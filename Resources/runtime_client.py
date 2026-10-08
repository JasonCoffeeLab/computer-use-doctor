"""Limited local MCP client for the existing node_repl. No arbitrary UI code input."""
import json,os,queue,subprocess,threading,time,re
from datetime import datetime,timezone
from pathlib import Path
import backend as b
from install_paths import own_app,codex_cli,node_command

RUNTIME=Path('/Applications/ChatGPT.app/Contents/Resources/cua_node')
PUBLIC_ENV={'BROWSER_USE_AVAILABLE_BACKENDS','BROWSER_USE_CODEX_APP_BUILD_FLAVOR','BROWSER_USE_CODEX_APP_VERSION','BROWSER_USE_TINYSKY_ENABLED','CODEX_CLI_PATH','CODEX_HOME','NODE_REPL_INSTRUCTIONS_USE_CASE_BROWSER','NODE_REPL_INSTRUCTIONS_USE_CASE_CHROME','NODE_REPL_INSTRUCTIONS_USE_CASE_COMPUTER_USE','NODE_REPL_NATIVE_PIPE_CONNECT_TIMEOUT_MS','NODE_REPL_NODE_MODULE_DIRS','NODE_REPL_NODE_PATH','NODE_REPL_TRUSTED_CODE_PATHS','NODE_REPL_TRUSTED_SERVICES','SKY_CUA_SERVICE_PATH'}

class RuntimeErrorSafe(Exception):pass

def stderr_hint(line):
    lower=line.lower()
    if 'invalid transport' in lower or 'error loading default config' in lower:
        return '官方 CLI 未能載入本次臨時設定；未啟動操作。這不是要求你重新批准。'
    if 'failed to initialize sqlite state runtime' in lower:
        return '官方 CLI 的本機狀態資料庫未能初始化；未開始操作，請核對官方 App 與資料目錄。'
    if lower.startswith('error:'):
        return '官方 CLI 啟動返回錯誤；未保存原始錯誤中的配置或秘密。'
    return None

class Client:
    def __init__(self,home):
        body=b.config_data(home).get('mcp_servers',{}).get('node_repl',{})
        command=body.get('command')
        if body.get('enabled') is False:raise RuntimeErrorSafe('現有 node_repl 配置停用，未自動開啟。')
        node_command(command)
        if body.get('args',[])!=[]:
            raise RuntimeErrorSafe('未取得符合已核對契約的 node_repl 執行檔，未執行任意配置命令。')
        environment={k:v for k,v in os.environ.items() if k in {'HOME','PATH','TMPDIR','LANG','LC_ALL','USER','LOGNAME','SHELL'}}
        configured=body.get('env',{})
        if not isinstance(configured,dict) or any(not isinstance(v,str) for v in configured.values()):raise RuntimeErrorSafe('執行環境格式未確認。')
        if set(configured)-PUBLIC_ENV:raise RuntimeErrorSafe('有未確認的執行環境欄位，不猜測或擴大設定。')
        environment.update(configured)
        self._start(command,[],environment,home)
    def _start(self,command,args,environment,cwd):
        self.proc=subprocess.Popen([command]+args,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=environment,cwd=str(cwd))
        self.messages=queue.Queue();self.counter=0
        self.transport_hint=None;self.stderr_done=threading.Event()
        def read():
            try:
                for line in self.proc.stdout:
                    self.messages.put(json.loads(line))
            except Exception:self.messages.put({'transport_invalid':True})
            finally:self.messages.put(None)
        threading.Thread(target=read,daemon=True).start()
        def read_stderr():
            try:
                for line in iter(lambda:self.proc.stderr.readline(4096),''):
                    hint=stderr_hint(line)
                    if hint and self.transport_hint is None:self.transport_hint=hint
            finally:self.stderr_done.set()
        threading.Thread(target=read_stderr,daemon=True).start()
    def transport_failure(self):
        self.stderr_done.wait(timeout=0.2)
        return RuntimeErrorSafe(self.transport_hint or '官方對接已中斷或返回格式無效；未取得本次有效结果。')
    def send(self,body):
        self.proc.stdin.write(json.dumps(body)+'\n');self.proc.stdin.flush()
    def request(self,method,params,timeout=20):
        self.counter+=1;identifier=self.counter
        self.send(dict(jsonrpc='2.0',id=identifier,method=method,params=params))
        end=time.monotonic()+timeout
        while True:
            try:item=self.messages.get(timeout=max(0,end-time.monotonic()))
            except queue.Empty:raise RuntimeErrorSafe('現有連接逾時，未取得本次操作結果。')
            if item is None or item.get('transport_invalid'):raise RuntimeErrorSafe('現有連接已中斷或回傳格式無效。')
            if item.get('id')!=identifier:continue
            if 'error' in item:raise RuntimeErrorSafe('連接返回協議錯誤；未偽造授權或改安全設定。')
            return item.get('result')
    def initialize(self):
        result=self.request('initialize',dict(protocolVersion='2025-06-18',capabilities={},clientInfo=dict(name='computer-use-doctor',version='8.0.0')))
        if not isinstance(result,dict) or result.get('protocolVersion') not in ('2025-06-18','2024-11-05','2024-10-07'):
            raise RuntimeErrorSafe('協議版本未確認。')
        self.send(dict(jsonrpc='2.0',method='notifications/initialized'))
        return self.request('tools/list',{})
    def close(self):
        try:self.proc.stdin.close()
        except Exception:pass
        try:self.proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.proc.terminate()
            try:self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:self.proc.kill();self.proc.wait()

def verify_node(home,nonce,client_type=None,app_path=None):
    if not isinstance(nonce,str) or not re.fullmatch(r'[0-9A-Fa-f-]{36}',nonce):
        raise ValueError('實測批次格式無效')
    report=dict(state='failed',phase='initialize',detail='未完成連接',route='node_repl + @oai/sky',
                generated_at=datetime.now(timezone.utc).isoformat(),nonce=nonce,clicks=0,screenshot='not_tested')
    client=None
    try:
        app=str(own_app(app_path))
        client=(client_type or Client)(home)
        tools=client.initialize()
        schema=next((t for t in tools.get('tools',[]) if t.get('name')=='js'),None)
        if not schema:raise RuntimeErrorSafe('連接初始化成功，但未公開 JS 工具。')
        report['phase']='native_connection'
        code=r"""
var phase='native_connection',clicks=0;
try {
 var sky=(await import('@oai/sky')).sky;
 var app=APP_PATH;
 var nonce=NONCE;
 var state=await sky.get_app_state({app,disableDiff:true});
 phase='read_interface';
 if(!state.text.includes('實測批次：'+nonce)) throw new Error('wrong_test_session');
 for(var label of ['實測：清除','實測：1','實測：加號','實測：1','實測：等號']) {
   var lines=state.text.split('\n').filter(x=>new RegExp('^\\s*\\d+\\s+button\\s+'+label+'$').test(x));
   var match=lines.length===1 && lines[0].match(/^\s*(\d+)\s+button\s/);
   if(!match) throw new Error('test_control_missing');
   phase='click';await sky.click({app,element_index:Number(match[1])});clicks++;
   state=await sky.get_app_state({app,disableDiff:true});
   if(!state.text.includes('實測批次：'+nonce)) throw new Error('test_session_changed');
 }
 phase='read_result';
 var batch=state.text.match(new RegExp('實測批次：'+nonce+'\\s+實測算式：(.*?)\\s+實測結果：([+-]?\\d+)\\s+實測點擊：(\\d+)(?=\\s|,|$)'));
 var pass=Boolean(batch && batch[1].trim()==='1 + 1' && batch[2]==='2' && batch[3]==='5');
 nodeRepl.write(JSON.stringify({doctor_runtime:true,state:pass?'passed':'failed',phase,clicks,nonce}));
} catch(e) {
 var reason=String(e.message||'');
 var known=['wrong_test_session','test_control_missing','test_session_changed'];
 nodeRepl.write(JSON.stringify({doctor_runtime:true,state:'failed',phase,clicks,nonce:NONCE,
   reason:reason.includes('native pipe')?'native_pipe_failed':known.includes(reason)?reason:'runtime_error'}));
}
""".replace('NONCE',json.dumps(nonce)).replace('APP_PATH',json.dumps(app))
        response=client.request('tools/call',dict(name='js',arguments=dict(code=code,timeout_ms=60000,title='Doctor 本次原生介面實測')),timeout=75)
        if not isinstance(response,dict) or response.get('isError'):raise RuntimeErrorSafe('JS 執行未完成；未取得本次原生操作證據。')
        payloads=[]
        for item in response.get('content',[]):
            if isinstance(item,dict) and item.get('type')=='text':
                try:payloads.append(json.loads(item.get('text','')))
                except (ValueError,TypeError):pass
        evidence=next((x for x in payloads if isinstance(x,dict) and x.get('doctor_runtime') is True and x.get('nonce')==nonce),None)
        if not evidence:raise RuntimeErrorSafe('未取得身份匹配的本次實測回讀，不沿用舊結果。')
        if evidence.get('phase') not in ('native_connection','read_interface','click','read_result'):
            raise RuntimeErrorSafe('實測階段無效。')
        report['phase']=evidence['phase'];report['clicks']=evidence.get('clicks',0)
        passed=evidence.get('state')=='passed' and evidence['phase']=='read_result' and evidence.get('clicks')==5
        report['state']='passed' if passed else 'failed'
        report['detail']='本次讀取、5次實際點擊及新結果回讀通過：1 + 1 = 2。截圖未驗證。' if passed else (
            '連接初始化成功，但原生操作通道啟動失敗；未執行點擊。不是舊入口停用的證明；未更改權限或安全設定。' if evidence.get('reason')=='native_pipe_failed'
            else '本次原生操作或結果核對失敗；不把配置正常當成操作通過。')
    except (RuntimeErrorSafe,OSError,ValueError,TypeError) as e:
        report['detail']=str(e) if isinstance(e,(RuntimeErrorSafe,ValueError)) else '原生實測執行失敗；未保存原始配置或介面內容。'
    finally:
        if client:client.close()
    return report

class NativeClient(Client):
    """Fixed existing Computer Use service. No arbitrary launcher or target input."""
    def __init__(self,home):
        self.deadline=time.monotonic()+45
        root,command=self.validate_config(home)
        environment={k:v for k,v in os.environ.items() if k in {'HOME','PATH','TMPDIR','LANG','LC_ALL','USER','LOGNAME','SHELL'}}
        environment['CODEX_HOME']=str(home)
        self._start(str(command),['mcp'],environment,root)
    @staticmethod
    def validate_config(home):
        body=b.config_data(home).get('mcp_servers',{}).get('computer-use',{})
        root=home/'computer-use'
        command=root/'Codex Computer Use.app/Contents/SharedSupport/SkyComputerUseClient.app/Contents/MacOS/SkyComputerUseClient'
        if body.get('enabled') is not True:raise RuntimeErrorSafe('獨立 computer-use 未明確啟用，未自動改設定。')
        if body.get('command')!=str(command) or body.get('cwd')!=str(root) or body.get('args')!=['mcp']:
            raise RuntimeErrorSafe('獨立入口與已核對的固定啟動契約不一致，未啟動未知命令。')
        if body.get('env',{}) or body.get('env_vars',[]):raise RuntimeErrorSafe('此固定原生入口出現未核對的額外環境設定。')
        if not command.is_file() or not os.access(command,os.X_OK):raise RuntimeErrorSafe('獨立 Computer Use 執行檔不存在或不可執行。')
        return root,command
    def request(self,method,params,timeout=15):
        remaining=self.deadline-time.monotonic()
        if remaining<=0:raise RuntimeErrorSafe('本次實測整體逾時，不繼續點擊。')
        return super().request(method,params,min(timeout,remaining))
    def call(self,name,arguments):
        result=self.request('tools/call',dict(name=name,arguments=arguments))
        if not isinstance(result,dict) or result.get('isError'):
            details=[]
            if isinstance(result,dict):
                details=[x.get('text','').splitlines()[0] for x in result.get('content',[]) if isinstance(x,dict) and x.get('type')=='text' and isinstance(x.get('text'),str) and x.get('text')]
            detail=b.redact(details[0])[:400] if details and 'Window:' not in details[0] else '未取得有效操作結果'
            raise RuntimeErrorSafe('原生工具 '+name+' 返回失敗：'+detail)
        return result

class AppServerClient(NativeClient):
    """Documented app-server RPC; truthful client, ephemeral context, no model turn."""
    def __init__(self,home,require_native=True):
        self.deadline=time.monotonic()+90
        self.require_native=require_native
        if require_native:self.validate_config(home)
        command=codex_cli(home)
        environment={k:v for k,v in os.environ.items() if k in {'HOME','PATH','TMPDIR','LANG','LC_ALL','USER','LOGNAME','SHELL'}}
        environment['CODEX_HOME']=str(home)
        arguments=['app-server','--stdio']
        if not require_native:
            # Scope only this ephemeral process. Never rewrite user config or approval rules.
            servers=b.config_data(home).get('mcp_servers',{})
            for name in sorted(servers):
                if not re.fullmatch(r'[A-Za-z0-9_-]+',name):
                    raise RuntimeErrorSafe('MCP 名稱不支援已核對的臨時覆寫語法，未啟動多餘入口。')
                if name!='node_repl':arguments+=['-c','mcp_servers.'+name+'.enabled=false']
        self._start(str(command),arguments,environment,'/private/tmp')
        self.thread_id=None
    def request(self,method,params,timeout=20):
        self.counter+=1;identifier=self.counter
        # App-server uses its own public JSON-RPC framing, without the jsonrpc field.
        self.send(dict(id=identifier,method=method,params=params))
        end=min(self.deadline,time.monotonic()+timeout)
        while True:
            try:item=self.messages.get(timeout=max(0,end-time.monotonic()))
            except queue.Empty:raise RuntimeErrorSafe('官方對接逾時，未繼續操作。')
            if item is None or item.get('transport_invalid'):raise self.transport_failure()
            if 'method' in item and 'id' in item:
                self.send(dict(id=item['id'],error=dict(code=-32000,message='Doctor cannot auto-approve an unexpected host request')))
                raise RuntimeErrorSafe('官方對接要求額外處理：'+str(item.get('method'))+'；未自動代批或擴大範圍。')
            if item.get('id')!=identifier:continue
            if 'error' in item:
                error=item['error']
                raise RuntimeErrorSafe('官方對接返回 '+str(error.get('code'))+'：'+b.redact(error.get('message',''))[:300])
            return item.get('result')
    def initialize(self):
        result=self.request('initialize',dict(clientInfo=dict(name='computer-use-doctor',title='Computer Use Doctor',version='9.0.1'),capabilities=dict(experimentalApi=True)))
        if not isinstance(result,dict):raise RuntimeErrorSafe('官方對接初始化未確認。')
        self.send(dict(method='initialized'))
        context=self.request('thread/start',dict(ephemeral=True,cwd='/private/tmp'),timeout=30)
        self.thread_id=context.get('thread',{}).get('id')
        if not isinstance(self.thread_id,str) or not self.thread_id:raise RuntimeErrorSafe('未取得本次官方臨時上下文。')
        rows=self.request('mcpServerStatus/list',dict(threadId=self.thread_id,detail='toolsAndAuthOnly'),timeout=30)
        self.server_rows=rows.get('data',[])
        if not self.require_native:return dict(tools=[])
        native=next((x for x in rows.get('data',[]) if x.get('name')=='computer-use'),None)
        if not native or not isinstance(native.get('tools'),dict):raise RuntimeErrorSafe('官方上下文未公開已指定的原生操作服務。')
        return dict(tools=list(native['tools'].values()))
    def call(self,name,arguments):
        if name not in ('get_app_state','click') or arguments.get('app')!=str(own_app()):
            raise RuntimeErrorSafe('超出本次固定實測工具或目標，不執行。')
        result=self.request('mcpServer/tool/call',dict(threadId=self.thread_id,server='computer-use',tool=name,arguments=arguments),timeout=20)
        if not isinstance(result,dict) or result.get('isError'):
            details=[x['text'] for x in (result or {}).get('content',[]) if isinstance(x,dict) and x.get('type')=='text' and isinstance(x.get('text'),str)] if isinstance(result,dict) else []
            raise RuntimeErrorSafe('官方原生工具 '+name+' 返回失敗：'+b.redact(details[0].splitlines()[0])[:400] if details else '官方原生工具未返回有效結果。')
        return result

class HostedNodeClient(AppServerClient):
    def __init__(self,home):
        node=b.config_data(home).get('mcp_servers',{}).get('node_repl',{})
        try:node_command(node.get('command'))
        except ValueError as exc:raise RuntimeErrorSafe(str(exc))
        if node.get('enabled') is False or node.get('args',[])!=[]:
            raise RuntimeErrorSafe('官方 Node 入口與已核對的固定契約不一致。')
        configured=node.get('env',{})
        if not isinstance(configured,dict) or set(configured)-PUBLIC_ENV or any(not isinstance(v,str) for v in configured.values()):
            raise RuntimeErrorSafe('Node 執行環境未匹配，不啟動未知配置。')
        super().__init__(home,require_native=False)
    def initialize(self):
        super().initialize()
        node=next((x for x in self.server_rows if x.get('name')=='node_repl'),None)
        if not node or not isinstance(node.get('tools'),dict) or 'js' not in node['tools']:
            raise RuntimeErrorSafe('官方上下文未公開既有 node_repl 的 JS 工具。')
        return dict(tools=list(node['tools'].values()))
    def request(self,method,params,timeout=20):
        if method=='tools/call':
            if params.get('name')!='js':raise RuntimeErrorSafe('只允許本次固定JS實測。')
            return super().request('mcpServer/tool/call',dict(threadId=self.thread_id,server='node_repl',tool='js',arguments=params['arguments']),timeout=timeout)
        return super().request(method,params,timeout=timeout)

def native_text(result):
    content=result.get('content')
    if not isinstance(content,list):raise RuntimeErrorSafe('原生工具未返回可核對的介面文字。')
    texts=[x['text'] for x in content if isinstance(x,dict) and x.get('type')=='text' and isinstance(x.get('text'),str)]
    if not texts:raise RuntimeErrorSafe('原生工具未返回可核對的介面文字。')
    return '\n'.join(texts)

def merge_native_state(previous,text):
    """Apply the provider's observed +/~/- AX changes to the current snapshot."""
    entries=[]
    for line in text.splitlines():
        match=re.match(r'^\s*([+~\-]?)\s*(\d+)\s+(.+)$',line)
        if match:entries.append((match[1],match[2],match[3]))
    # A fresh root without a diff marker establishes a complete replacement tree.
    full=not any(marker for marker,_,_ in entries) and any(index=='0' and ('window' in body or 'dialog' in body or 'sheet' in body) for _,index,body in entries)
    current={} if full else dict(previous)
    for marker,index,body in entries:
        if marker=='-':current.pop(index,None)
        else:current[index]=body
    return current

def state_text(current):
    return '\n'.join(index+' '+body for index,body in current.items())

def verify_legacy(home,nonce):
    if not isinstance(nonce,str) or not re.fullmatch(r'[0-9A-Fa-f-]{36}',nonce):raise ValueError('實測批次格式無效')
    report=dict(state='failed',phase='initialize',detail='本次原生實測尚未完成',route='Codex App Server → computer-use',
                generated_at=datetime.now(timezone.utc).isoformat(),nonce=nonce,clicks=0,screenshot='not_tested')
    client=None
    try:
        client=AppServerClient(home)
        listing=client.initialize()
        schemas={x.get('name'):x.get('inputSchema',{}) for x in listing.get('tools',[]) if isinstance(x,dict)}
        for name in ('get_app_state','click'):
            if schemas.get(name,{}).get('properties',{}).get('app',{}).get('type')!='string':raise RuntimeErrorSafe('原生工具的目標契約未匹配，未猜測操作。')
        if schemas['click'].get('properties',{}).get('element_index',{}).get('type')!='string':raise RuntimeErrorSafe('原生點擊索引契約改變，未使用過期參數。')
        app=str(own_app())
        report['phase']='read_interface'
        snapshot=merge_native_state({},native_text(client.call('get_app_state',dict(app=app))))
        text=state_text(snapshot)
        def check_batch(text):
            if '實測批次：'+nonce not in text:raise RuntimeErrorSafe('實測批次或視窗不一致，未沿用舊結果。')
        check_batch(text)
        for label in ['實測：清除','實測：1','實測：加號','實測：1','實測：等號']:
            matches=[re.match(r'^\s*(\d+)\s+button\s+(.+)$',line) for line in text.splitlines()]
            matches=[m for m in matches if m and m[2].strip()==label]
            if len(matches)!=1:raise RuntimeErrorSafe('本次實測按鍵未唯一定位，不猜索引或座標。')
            report['phase']='click'
            client.call('click',dict(app=app,element_index=matches[0][1]))
            report['clicks']+=1
            report['phase']='read_result'
            until=time.monotonic()+4
            observed_formats=[]
            while True:
                # Read-only settling: never repeat a click with unknown effects.
                time.sleep(0.25)
                raw=native_text(client.call('get_app_state',dict(app=app)))
                observed_formats.extend(b.redact(x.group()) for x in re.finditer(r'.{0,70}實測(?:結果|算式|點擊).{0,75}',raw))
                snapshot=merge_native_state(snapshot,raw)
                text=state_text(snapshot)
                check_batch(text)
                observed=re.search(r'實測點擊：(\d+)(?![\d.])',text)
                if observed and int(observed[1])==report['clicks']:break
                if time.monotonic()>=until:
                    raise RuntimeErrorSafe('操作返回後未讀回本次點擊計數，停止而不重點。固定字段格式：'+' / '.join(observed_formats[:3]))
        expression=re.search(r'實測算式：([0-9+ \u3000]+)',text)
        result_value=re.search(r'實測結果：([+-]?\d+)(?![\d.])',text)
        count_value=re.search(r'實測點擊：(\d+)(?![\d.])',text)
        values=(expression[1].strip() if expression else None,int(result_value[1]) if result_value else None,int(count_value[1]) if count_value else None)
        if values!=('1 + 1',2,5):
            raise RuntimeErrorSafe('本次5次點擊後未核對一致，不宣稱通過。已解析固定字段：'+str(values))
        report['state']='passed'
        report['detail']='本次原生介面讀取、5次實際點擊及新結果回讀通過：1 + 1 = 2。截圖未另行驗證。'
    except (RuntimeErrorSafe,OSError,ValueError,TypeError,KeyError) as e:
        report['detail']=str(e) if isinstance(e,RuntimeErrorSafe) else '原生連接或資料解析失敗；未記錄原始配置與介面內容。'
    finally:
        if client:client.close()
    return report

def verify(home,nonce,app_path=None):
    report=verify_node(home,nonce,HostedNodeClient,app_path)
    report['route']='Codex App Server → node_repl + @oai/sky'
    return report
