"""V9 diagnostics, monitoring decisions and bounded cache transactions."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import uuid
import contextlib
import fcntl
from datetime import datetime, timezone
from repair_core import cache_ready, replace_latest
sys.path.insert(0, str(Path(__file__).parent / 'vendor'))
import tomli

NAMES = ('browser', 'chrome', 'computer-use', 'unified-computer-use')


def config_data(home):
    path = home / 'config.toml'
    if not path.is_file():
        return {}
    try:
        data=tomli.loads(path.read_text())
        for key in ('marketplaces','plugins','mcp_servers'):
            if key in data and (not isinstance(data[key],dict) or any(not isinstance(value,dict) for value in data[key].values())):
                raise ValueError('不支援的配置形態')
        return data
    except (OSError, ValueError):
        raise ValueError('配置無法完整解析；不把解析失敗當成缺配置，不執行修復')


def atomic_json(path, data):
    temporary=path.parent/('.receipt-'+uuid.uuid4().hex)
    path.parent.mkdir(parents=True,exist_ok=True)
    with temporary.open('x',encoding='utf-8') as stream:
        os.chmod(temporary,0o600)
        json.dump(data,stream,ensure_ascii=False,indent=2)
        stream.flush();os.fsync(stream.fileno())
    os.replace(temporary,path)


@contextlib.contextmanager
def mutation_lock(home):
    if home.resolve() in (Path('/'),Path.home().resolve()) or not home.is_dir():
        raise ValueError('無效修復根目錄')
    directory=home/'computer-use-doctor-v3'
    if not confined(directory,home) or directory.is_symlink():
        raise ValueError('交易記錄路徑不安全')
    directory.mkdir(exist_ok=True)
    if not confined(directory/'receipts',home) or (directory/'receipts').is_symlink():
        raise ValueError('收據目錄不安全')
    fd=os.open(directory/'operation.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('另一個修復／恢復正在執行，請等待，不並行覆蓋')
        yield
    finally:
        os.close(fd)


def redact(value):
    value = re.sub(r'(https?://)[^/\s@]+@', r'\1[redacted]@', str(value))
    value = re.sub(r'(?i)(token|password|secret|api[_-]?key)(\s*[=:]\s*)[^\s,;]+', r'\1\2[redacted]', value)
    return value


def manifest(path):
    try:
        data = json.loads((path / '.codex-plugin/plugin.json').read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def table(text, header):
    match = re.search(r'^\[' + re.escape(header) + r'\]\s*\n(.*?)(?=^\[|\Z)', text, re.M | re.S)
    return match.group(1) if match else ''


def string_value(text, key):
    match = re.search(r'^\s*' + re.escape(key) + r'\s*=\s*("(?:[^"\\]|\\.)*"|\'[^\']*\')', text, re.M)
    if not match:
        return None
    raw = match.group(1)
    try:
        return json.loads(raw) if raw.startswith('"') else raw[1:-1]
    except ValueError:
        return None


def fingerprint(path):
    path = Path(path)
    if path.is_symlink():
        return 'link:' + os.readlink(path)
    if not path.exists():
        return 'missing'
    if not path.is_dir():
        return 'file:' + hashlib.sha256(path.read_bytes()).hexdigest()
    digest = hashlib.sha256()
    for item in sorted(path.rglob('*')):
        if item.name in ('.DS_Store', '__pycache__') or '__pycache__' in item.parts:
            continue
        relative = str(item.relative_to(path))
        digest.update(relative.encode())
        if item.is_symlink():
            digest.update(('link:' + os.readlink(item)).encode())
        elif item.is_file():
            digest.update(str(item.stat().st_mode & 0o777).encode())
            with item.open('rb') as stream:
                while True:
                    block = stream.read(1024 * 1024)
                    if not block:
                        break
                    digest.update(block)
        elif item.is_dir():
            digest.update(b'directory')
    return digest.hexdigest()


def confined(path, root):
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def inspect_materialized_mcp(source,target):
    """Read-only binding evidence, not an execution or publisher-trust claim."""
    try:
        a=json.loads((source/'.mcp.json').read_text());z=json.loads((target/'.mcp.json').read_text())
        if not isinstance(a,dict) or not isinstance(z,dict) or set(a)!=set(z):return False,'連接設定的頂層結構不同；未覆蓋。'
        original=a.get('mcpServers');material=z.get('mcpServers')
        if not isinstance(original,dict) or not isinstance(material,dict) or set(original)!=set(material):return False,'工具項目清單不同；需核對，未覆蓋。'
        for name,stub in original.items():
            body=material[name]
            if not isinstance(stub,dict) or not isinstance(body,dict):return False,'工具設定格式不完整。'
            if stub==body:continue
            if name!='cua_repl' or stub.get('command')!='node' or stub.get('enabled') is not False or stub.get('args',[])!=[]:
                return False,'不是已辨識的未綁定 cua_repl 範本；未猜測設定。'
            command=body.get('command');args=body.get('args')
            if not isinstance(command,str) or not command.startswith('/') or not isinstance(args,list) or len(args)!=1 or not isinstance(args[0],str) or not args[0].startswith('/'):
                return False,'啟動命令或入口參數未能完整核對。'
            executable=Path(command);entry=Path(args[0]);runtime=executable.parent.parent
            if executable.name!='node' or runtime.name!='cua_node' or not executable.is_file() or not os.access(executable,os.X_OK) or not entry.is_file() or not confined(entry,runtime):
                return False,'內置執行檔、入口或路徑範圍未通過核對。'
            package=entry.parent.parent
            meta=json.loads((package/'package.json').read_text())
            if not isinstance(meta,dict) or meta.get('name')!='@oai/cua-repl' or not isinstance(meta.get('bin'),dict) or meta['bin'].get('cua-repl') is None:
                return False,'入口套件身份或 bin 宣告不匹配。'
            declared=package/meta['bin']['cua-repl']
            if not confined(declared,package) or declared.resolve()!=entry.resolve():return False,'入口與套件宣告不一致。'
            if body.get('enabled') is not True:return False,'快取內的連接仍未啟用；保留狀態，不自動開啟。'
            if 'env' in body and (not isinstance(body['env'],dict) or any(not isinstance(v,str) for v in body['env'].values())):
                return False,'注入環境格式未通過核對。'
            if 'env_vars' in body and (not isinstance(body['env_vars'],list) or any(not isinstance(v,str) for v in body['env_vars'])):
                return False,'環境變數名稱清單格式未通過核對。'
            if set(body)-set(stub)-{'args','env','env_vars'}:return False,'還有未辨識的新增設定欄位。'
        return True,'已核對範本至內置 cua_repl 的命令、入口、套件宣告及環境格式；保留平台綁定，不覆蓋。環境語意、協議連線與畫面操作未執行驗證。'
    except (OSError,ValueError,TypeError,KeyError):return False,'連接差異核對未完成；檔案、入口或格式有缺口，未覆蓋。'


def plugin_diagnostics(home):
    config = home / 'config.toml'
    data=config_data(home)
    source_text = data.get('marketplaces',{}).get('openai-bundled',{}).get('source')
    if source_text is not None and not isinstance(source_text,str):
        raise ValueError('插件來源配置不是有效路徑字串，未執行修復')
    source_root = Path(source_text).expanduser() if source_text else home / '.tmp/bundled-marketplaces/openai-bundled'
    rows, actions = [], []
    for name in NAMES:
        enabled = data.get('plugins',{}).get(name+'@openai-bundled',{}).get('enabled') is True
        source = source_root / 'plugins' / name
        meta = manifest(source)
        version = meta.get('version')
        valid_version = isinstance(version, str) and bool(re.fullmatch(r'\d+(?:\.\d+)+', version))
        base = home / 'plugins/cache/openai-bundled' / name
        target = base / version if valid_version else None
        source_ok = bool(valid_version and meta.get('name') == name and
                         cache_ready(name, source, 'darwin', source))
        safe_paths = bool(confined(base, home) and confined(source,home) and not base.is_symlink() and
                          (not target or (confined(target, base) and not target.is_symlink())))
        ready = bool(target and safe_paths and source_ok and cache_ready(name, target, 'darwin', source))
        materialized_difference=False
        binding_checked=False;binding_detail=''
        if target and target.is_dir() and manifest(target).get('version')==version:
            materialized_difference=manifest(target)!=meta
            if (source/'.mcp.json').is_file() and (target/'.mcp.json').is_file():
                materialized_difference=materialized_difference or (source/'.mcp.json').read_bytes()!=(target/'.mcp.json').read_bytes()
            if materialized_difference and manifest(target)==meta and safe_paths and source_ok:
                binding_checked,binding_detail=inspect_materialized_mcp(source,target)
                if binding_checked:
                    binding_checked=cache_ready(name,target,'darwin',source,ignored_files=('.mcp.json',))
                    if not binding_checked:binding_detail='連接差異已分析，但其他快取檔案不完整；保留綁定，未直接覆蓋。'
                    else:ready=True
        latest = base / 'latest'
        linked = bool(target and latest.is_symlink() and latest.resolve() == target.resolve())
        # A valid manifest may refer to platform-rewritten material. Never replace it blindly.
        repairable = bool(enabled and source_ok and safe_paths and (not materialized_difference or binding_checked) and (not ready or not linked))
        state = 'checked' if enabled and ready and linked else ('warning' if repairable else 'unknown')
        if not enabled:
            state='disabled'
            detail = '未啟用；請在官方插件設定核對，不自動扩大存取。'
        elif not source_ok:
            detail = '缺少完整同版本來源或版本格式未確認；不猜測、不重裝。'
        elif not safe_paths:
            detail = '快取路徑或連結超出預期範圍；停止該項修復。'
        elif materialized_difference:
            state=('configured' if linked else 'warning') if binding_checked else 'unknown'
            detail=binding_detail or '插件描述檔有差異，不只連接設定；需核對差異來源，未直接覆蓋。'
            if binding_checked and not linked:detail+=' latest 連結未匹配，可只修復連結並保留此配置。'
        elif not ready:
            detail = '快取缺少或不同於來源檔案；可核對修復，但不等同實際運行故障。'
        elif not linked:
            detail = '快取結構通過，latest 未指向來源版本。'
        else:
            detail = '本機來源、快取結構及版本連結一致；實際操作仍需另驗。'
        row = dict(name=name, enabled=enabled, version=version if isinstance(version,str) else '未取得',
                   state=state, detail=detail, repairable=repairable)
        rows.append(row)
        if repairable:
            actions.append(dict(name=name, version=version, source=str(source),
                                base=str(base), target=str(target), rebuild=not ready,
                                source_hash=fingerprint(source), target_hash=fingerprint(target),
                                latest_hash=fingerprint(latest)))
    scope = dict(config_hash=fingerprint(config), actions=actions)
    plan_id = hashlib.sha256(json.dumps(scope, sort_keys=True).encode()).hexdigest()
    return rows, actions, plan_id


def mcp_diagnostics(home):
    data=config_data(home)
    rows = []
    for name, body in data.get('mcp_servers',{}).items():
        enabled = body.get('enabled') is not False
        command = body.get('command')
        if command is not None and not isinstance(command,str):
            rows.append(dict(name=name,state='unknown',detail='命令欄位格式不支援；未當成缺件修復。'))
            continue
        if not enabled:
            state, detail = 'disabled', '已確認配置明確設為停用；不是未知故障，不自動啟用。'
        elif command and command.startswith('/'):
            usable = Path(command).is_file() and os.access(command, os.X_OK)
            state, detail = ('checked', '命令檔案存在且可執行；尚未啟動或驗證協議。') if usable else ('warning', '絕對路徑命令不存在或不可執行。')
        elif command and command.startswith('.'):
            state, detail = 'unknown', '相對命令依賴工作目錄；不能只憑字串判定可用。'
        elif command:
            state, detail = ('checked', 'PATH 找到命令；尚未啟動或驗證協議。') if shutil.which(command) else ('warning', 'PATH 未找到命令。')
        else:
            state, detail = 'unknown', '遠端或其他配置形態；未讀取秘密、未連線。'
        rows.append(dict(name=name.strip('"'), state=state, detail=detail))
    return rows


def browser_diagnostics():
    path = Path.home() / 'Library/Application Support/Google/Chrome/NativeMessagingHosts/com.openai.codexextension.json'
    try:
        data = json.loads(path.read_text())
        if not isinstance(data,dict):raise ValueError('invalid native host descriptor')
        executable = data.get('path', '')
        valid = (data.get('name') == 'com.openai.codexextension' and
                 isinstance(executable, str) and Path(executable).is_file() and os.access(executable, os.X_OK))
        return [dict(name='Chrome 原生連接', state='checked' if valid else 'warning',
                     detail='連接描述及執行檔可用；未讀取瀏覽器資料或驗證連線。' if valid else '連接描述或執行檔需核對。')]
    except (OSError, ValueError):
        return [dict(name='Chrome 原生連接', state='unknown', detail='未取得有效連接描述；不讀取瀏覽器帳號或分頁。')]


def source_approval(home):
    config=config_data(home)
    configured=config.get('marketplaces',{}).get('openai-bundled',{}).get('source')
    root=Path(configured).expanduser() if configured else home/'.tmp/bundled-marketplaces/openai-bundled'
    result={}
    for name in NAMES:
        version=manifest(root/'plugins'/name).get('version')
        result[name]=dict(version=version if isinstance(version,str) else None,hash=fingerprint(root/'plugins'/name),
                          enabled=config.get('plugins',{}).get(name+'@openai-bundled',{}).get('enabled') is True)
    return result


def diagnose(home, probe=True):
    rows, actions, plan_id = plugin_diagnostics(home)
    approval_sources=source_approval(home)
    return dict(version='V9', generated_at=datetime.now(timezone.utc).isoformat(),
                plugins=rows, mcp=mcp_diagnostics(home), network=[],
                browser=browser_diagnostics() if probe else [],
                repair_count=len(actions), plan_id=plan_id,
                approval_sources=approval_sources,
                transaction_history=history(home)['transactions'], probes_completed=probe,
                boundary='只讀診斷；結構正常不代表實際操作或Jarvis委派正常。')


def classify(text):
    checks = (
        ('website_policy', ('not permitted on', '網站權限', 'blocked by saved user'),
         '網站存取被限制', '核對發生錯誤的瀏覽器和目的地權限；不以改工具繞過拒絕。'),
        ('authorization_evidence', ('relayed authorization', '授權證據', '代轉授權', 'original task instructions'),
         '授權來源或範圍待核', '對帳原始人類指令、範圍變更、目標和代轉內容；不偽造批准。'),
        ('capability_missing', ('tool unavailable', 'tools missing', '缺少工具', 'not exposed', '沒有工具'),
         '執行端缺少工具', '比較本機與dot任務的實際工具清單；本機成功不證明子任務可用。'),
        ('transport', ('transport', 'reconnecting', '連線失敗', 'offline', 'timeout'),
         '連線或逾時候選', '核對主機、連接和網路。逾時不等於授權不足，也不等於不安全。'),
        ('explicit_rejection', ('unacceptable risk', 'do not bypass', '明確拒絕'),
         '明確安全拒絕', '按正式途徑核對原因或補證；不得換路徑追求同一被拒動作。'),
    )
    lower = text.lower()
    matches = [dict(kind=kind, title=title, next_step=next_step)
               for kind, tokens, title, next_step in checks if any(token in lower for token in tokens)]
    return dict(matches=matches, boundary='本機文字分類，不代表根因已確認；未讀取Jarvis歷史或自動發訊。')


def repair_transaction(home, expected_plan, confirmed=False):
    if not confirmed:
        raise ValueError('須由使用者確認本次快取修復範圍')
    if home.resolve() in (Path('/'), Path.home().resolve()) or (home / 'config.toml').is_symlink():
        raise ValueError('不接受廣泛根目錄或連結配置')
    rows, actions, plan_id = plugin_diagnostics(home)
    if expected_plan != plan_id:
        raise ValueError('診斷後來源／配置／快取已改變，請重新檢查，不執行過期方案')
    transaction = uuid.uuid4().hex
    receipts = []
    report_dir=home/'computer-use-doctor-v3/receipts'
    record=dict(transaction=transaction,status='prepared',created_at=datetime.now(timezone.utc).isoformat(),receipts=receipts)
    receipt_path=report_dir/(transaction+'.json')
    atomic_json(receipt_path,record)
    for action in actions:
        base, source, target = map(Path, (action['base'], action['source'], action['target']))
        base.mkdir(parents=True, exist_ok=True)
        stage = base / ('.doctor-stage-' + transaction)
        original = None
        item=dict(name=action['name'],version=action['version'],target=str(target),
                  original=None,latest_directory=None,previous_link=None,
                  previous_latest_missing=action['latest_hash']=='missing',
                  before_target_hash=action['target_hash'],before_latest_hash=action['latest_hash'],phase='prepared')
        receipts.append(item)
        atomic_json(receipt_path,record)
        try:
            if fingerprint(source)!=action['source_hash'] or fingerprint(target)!=action['target_hash'] or fingerprint(base/'latest')!=action['latest_hash']:
                raise ValueError('寫入前狀態已變，不覆蓋新內容')
            if action['rebuild']:
                if target.is_symlink() or not confined(target, home):
                    raise ValueError('目標路徑不安全')
                shutil.copytree(source, stage, symlinks=True)
                if not cache_ready(action['name'], stage, 'darwin', source) or fingerprint(stage) != action['source_hash']:
                    raise ValueError('候選快取驗證不一致，未替換原快取')
                if target.exists():
                    original = base / (target.name + '.bak-doctor-' + transaction)
                    item['original']=str(original);item['phase']='target_backup_pending'
                    atomic_json(receipt_path,record)
                    os.replace(target, original)
                item['phase']='target_replace_pending';atomic_json(receipt_path,record)
                try:
                    os.replace(stage, target)
                except OSError:
                    if original:
                        os.replace(original, target)
                    raise
            def backup(path):
                return base / ('latest.bak-doctor-' + transaction)
            old_latest = base / 'latest'
            old_link = os.readlink(old_latest) if old_latest.is_symlink() else None
            item['previous_link']=old_link;item['phase']='latest_replace_pending'
            item['latest_directory']=str(backup(old_latest)) if old_latest.exists() and not old_latest.is_symlink() else None
            atomic_json(receipt_path,record)
            preserved_latest = replace_latest(base, target, backup)
            item.update(latest_directory=str(preserved_latest) if preserved_latest else None,
                        after_target_hash=fingerprint(target),after_latest_hash=fingerprint(base/'latest'),phase='complete')
            record['status']='in_progress';atomic_json(receipt_path,record)
        except Exception:
            item['failure_phase']=item['phase'];item['phase']='needs_review'
            record['status']='partial_or_failed';atomic_json(receipt_path,record)
            raise
    if receipts:
        record['status']='cache_repaired';atomic_json(receipt_path,record)
    else:
        record['status']='no_changes';atomic_json(receipt_path,record)
    return dict(transaction=transaction, repaired=len(receipts), diagnostic=diagnose(home, False),
                boundary='只修快取和版本連結；配置、服務等級、權限與代理未改，運行未驗。')


def restore_transaction(home, transaction, confirmed=False):
    if not confirmed or not re.fullmatch(r'[0-9a-f]{32}', transaction):
        raise ValueError('需要確認精確的恢復交易')
    receipt_path=home/'computer-use-doctor-v3/receipts'/(transaction+'.json')
    record=json.loads(receipt_path.read_text())
    if record.get('status') != 'cache_repaired':
        raise ValueError('未完成或已恢復交易需人工核對，不自動處理')
    # Preflight every item before restoring any item.
    for item in record['receipts']:
        target=Path(item['target']); base=target.parent
        if item['name'] not in NAMES or base != home/'plugins/cache/openai-bundled'/item['name']:
            raise ValueError('恢復目標不匹配')
        if not re.fullmatch(r'\d+(?:\.\d+)+',item.get('version','')) or target.name!=item['version']:
            raise ValueError('恢復版本不匹配')
        if not confined(base,home) or fingerprint(target)!=item['after_target_hash'] or fingerprint(base/'latest')!=item['after_latest_hash']:
            raise ValueError('修復後內容已改變，拒絕覆蓋新內容')
        for field in ('original','latest_directory'):
            expected=base/(target.name+'.bak-doctor-'+transaction) if field=='original' else base/('latest.bak-doctor-'+transaction)
            if item[field] and Path(item[field])!=expected:
                raise ValueError('備份名稱不匹配')
            if item[field] and (Path(item[field]).parent != base or not Path(item[field]).exists() or not confined(Path(item[field]),home)):
                raise ValueError('備份缺失或不在預期範圍')
            expected_hash=item['before_target_hash'] if field=='original' else item['before_latest_hash']
            if item[field] and fingerprint(Path(item[field]))!=expected_hash:
                raise ValueError('備份內容已改變，不用未核對備份覆蓋快取')
    record['status']='restoring';atomic_json(receipt_path,record)
    for item in reversed(record['receipts']):
        target=Path(item['target']);base=target.parent; latest=base/'latest'
        retained=base/('.doctor-restored-link-'+transaction)
        try:
            item['phase']='restore_latest_pending';atomic_json(receipt_path,record)
            if item['latest_directory']:
                os.replace(latest,retained)
                try:os.replace(Path(item['latest_directory']),latest)
                except OSError:
                    os.replace(retained,latest);raise
            elif item['previous_link'] is not None:
                temporary=base/('.doctor-restore-stage-'+transaction)
                temporary.symlink_to(item['previous_link'])
                try:os.replace(temporary,latest)
                finally:
                    if temporary.is_symlink():temporary.unlink()
            else:
                os.replace(latest,retained)
            if item['original']:
                item['phase']='restore_target_pending';atomic_json(receipt_path,record)
                preserved=base/(target.name+'.after-doctor-'+transaction)
                os.replace(target,preserved)
                try:os.replace(Path(item['original']),target)
                except OSError:
                    os.replace(preserved,target);raise
            item['phase']='restored';atomic_json(receipt_path,record)
        except Exception:
            item['failure_phase']=item['phase'];item['phase']='needs_review'
            record['status']='restore_partial_or_failed';atomic_json(receipt_path,record)
            raise
    record['status']='restored'
    atomic_json(receipt_path,record)
    return dict(restored=len(record['receipts']),boundary='已恢復原版本連結及有備份的快取；新增快取保留，不刪資料。')


def history(home):
    rows=[]
    for path in sorted((home/'computer-use-doctor-v3/receipts').glob('*.json'), reverse=True):
        try:
            if path.is_symlink():raise ValueError('unsafe receipt')
            data=json.loads(path.read_text())
            if not isinstance(data,dict) or not isinstance(data.get('receipts'),list) or not isinstance(data.get('status'),str) or any(not isinstance(item,dict) for item in data['receipts']):
                raise ValueError('invalid receipt')
            if data.get('transaction') != path.stem or not re.fullmatch(r'[0-9a-f]{32}',path.stem) or not isinstance(data.get('created_at'),str):
                raise ValueError('invalid receipt identity')
            if any(not isinstance(item.get('name'),str) or not isinstance(item.get('phase'),str) or ('failure_phase' in item and not isinstance(item['failure_phase'],str)) for item in data['receipts']):
                raise ValueError('invalid receipt steps')
            rows.append(dict(transaction=data.get('transaction'),status=data.get('status'),count=len(data.get('receipts',[])),created_at=data.get('created_at',''),
                             steps=[item.get('name','未識別')+': '+item.get('failure_phase',item.get('phase','unknown')) for item in data.get('receipts',[])]))
        except (OSError,ValueError,TypeError):
            rows.append(dict(transaction=path.stem,status='unreadable',count=0,created_at='',steps=['收據無法核對，保留原檔，不自動重做。']))
    return dict(transactions=sorted(rows,key=lambda row:row['created_at'],reverse=True))


def repair(home,plan,confirmed=False):
    if not confirmed:raise ValueError('需要確認修復範圍')
    with mutation_lock(home):
        if any(item['status'] not in ('cache_repaired','restored','no_changes')
               for item in history(home)['transactions']):
            raise ValueError('存在未完成交易；先核對備份與停點，不覆蓋或重做')
        return repair_transaction(home,plan,confirmed)


def restore(home,transaction,confirmed=False):
    if not confirmed:raise ValueError('需要確認恢復範圍')
    with mutation_lock(home):
        if any(item['status'] not in ('cache_repaired','restored','no_changes') for item in history(home)['transactions']):
            raise ValueError('存在未完成或不可讀交易；先核對停點，不與恢復交錯寫入')
        return restore_transaction(home,transaction,confirmed)


def auto_decision(current, previous_plan, approved_sources, attempted_plans, cooldown=False):
    """Pure eligibility gate, not an independent authority grant."""
    def enabled_scope(sources):
        if not isinstance(sources,dict):return None
        if any(not isinstance(value,dict) or not isinstance(value.get('enabled'),bool) for value in sources.values()):return None
        return {name:value for name,value in sources.items() if value['enabled']}
    current_scope=enabled_scope(current.get('approval_sources'))
    approved_scope=enabled_scope(approved_sources)
    if current_scope is None or approved_scope is None or current_scope!=approved_scope:
        return dict(eligible=False,pause=True,code='scope_changed',reason='來源版本、指紋或插件啟用清單改變；暫停自動修復，重新核對範圍。')
    if current.get('transaction_blocked',False) or any(row.get('status') not in ('cache_repaired','restored','no_changes') for row in current.get('transaction_history',[])):
        return dict(eligible=False,pause=True,code='transaction_blocked',reason='存在未完成或不可讀交易；暫停自動修復，先核對停點。')
    if current.get('repair_count',0)==0:
        return dict(eligible=False,code='no_fault',reason='沒有可確認的快取問題；其他連線／權限疑點只提示。')
    if current.get('plan_id')!=previous_plan:
        return dict(eligible=False,code='waiting',reason='第一次觀察或狀態有變，等待下一次穩定檢查。')
    if current.get('plan_id') in attempted_plans:
        return dict(eligible=False,code='same_plan',reason='同一方案已嘗試，不反覆修復；保留結果供核對。')
    if cooldown:
        return dict(eligible=False,code='cooldown',reason='修復冷卻中，繼續監測，不連續更改快取。')
    return dict(eligible=True,code='eligible',reason='來源及啟用清單在確認範圍、兩次狀態一致，可作定向快取修復。')


EVENT_ACTIONS={'diagnose','repair','restore','classify','history','auto-decision'}
EVENT_CODES={'returned','failed','scope_changed','transaction_blocked','no_fault','waiting','same_plan','cooldown','eligible'}

def event_history(home):
    path=home/'computer-use-doctor-v3/events-v6.json'
    if not confined(path,home) or path.is_symlink():raise ValueError('處理紀錄路徑不安全')
    if not path.exists():return dict(events=[])
    try:
        data=json.loads(path.read_text())
        if not isinstance(data,dict) or not isinstance(data.get('events'),list):raise ValueError('invalid event log')
        if any(not isinstance(row,dict) or set(row)!={'created_at','action','code'} or row['action'] not in EVENT_ACTIONS or row['code'] not in EVENT_CODES or not isinstance(row['created_at'],str) for row in data['events']):
            raise ValueError('invalid event log')
        for row in data['events']:datetime.fromisoformat(row['created_at'])
        return dict(events=data['events'][-200:])
    except (OSError,ValueError,TypeError):raise ValueError('處理紀錄無法核對，保留原檔，不覆蓋。')

def record_event(home,request):
    if not isinstance(request,dict) or set(request)!={'action','code'} or request['action'] not in EVENT_ACTIONS or request['code'] not in EVENT_CODES:
        raise ValueError('處理紀錄只接受固定動作與結果代碼，不記錄原始輸入。')
    with mutation_lock(home):
        rows=event_history(home)['events']
        rows.append(dict(created_at=datetime.now(timezone.utc).isoformat(),**request))
        atomic_json(home/'computer-use-doctor-v3/events-v6.json',dict(events=rows[-200:]))
        return dict(events=rows[-200:])


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['diagnose','classify','repair','history','restore','auto-decision','record-event','event-history','runtime-verify'])
    parser.add_argument('--nonce',default='')
    parser.add_argument('--app-path',type=Path)
    parser.add_argument('--home',type=Path,default=Path.home()/'.codex')
    parser.add_argument('--no-probe',action='store_true')
    parser.add_argument('--plan',default='')
    parser.add_argument('--transaction',default='')
    parser.add_argument('--confirmed',action='store_true')
    args=parser.parse_args()
    try:
        if args.action=='runtime-verify':
            from runtime_client import verify
            result=verify(args.home,args.nonce,args.app_path)
        elif args.action=='diagnose':result=diagnose(args.home,not args.no_probe)
        elif args.action=='classify':result=classify(sys.stdin.read(64000))
        elif args.action=='repair':result=repair(args.home,args.plan,args.confirmed)
        elif args.action=='restore':result=restore(args.home,args.transaction,args.confirmed)
        elif args.action=='auto-decision':
            request=json.loads(sys.stdin.read(64000))
            result=auto_decision(request['current'],request.get('previous_plan'),request.get('approved_sources'),request.get('attempted_plans',[]),request.get('cooldown',False))
        elif args.action=='record-event':result=record_event(args.home,json.loads(sys.stdin.read(64000)))
        elif args.action=='event-history':result=event_history(args.home)
        else:result=history(args.home)
        print(json.dumps(dict(ok=True,data=result),ensure_ascii=False))
    except Exception as exc:
        message=str(exc) if isinstance(exc,ValueError) else '操作失敗；請檢查權限／備份及交易停點，不盲目重試。'
        print(json.dumps(dict(ok=False,error=redact(message)),ensure_ascii=False))
        sys.exit(1)


if __name__=='__main__':main()
