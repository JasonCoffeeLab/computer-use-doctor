import unittest,json,sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Resources'))
import runtime_client as r
import plistlib

NONCE='12345678-1234-1234-1234-123456789abc'
APP='/Applications/Computer Use Doctor V9 Preview.app'
class FakeClient:
    response=None
    code=''
    closed=False
    def __init__(self,home):pass
    def initialize(self):return {'tools':[{'name':'js'}]}
    def request(self,method,params,timeout):
        FakeClient.code=params['arguments']['code']
        return FakeClient.response
    def close(self):FakeClient.closed=True

class RuntimeTests(unittest.TestCase):
    def setUp(self):
        own=patch.object(r,'own_app',return_value=Path(APP));own.start();self.addCleanup(own.stop)
    def run_evidence(self,evidence,is_error=False):
        FakeClient.response={'isError':is_error,'content':[{'type':'text','text':json.dumps(evidence)}]}
        FakeClient.closed=False
        with patch.object(r,'Client',FakeClient):result=r.verify_node(Path('/tmp'),NONCE)
        self.assertTrue(FakeClient.closed)
        return result
    def test_pass_requires_new_result_and_five_clicks(self):
        result=self.run_evidence(dict(doctor_runtime=True,state='passed',phase='read_result',nonce=NONCE,clicks=5))
        self.assertEqual(result['state'],'passed');self.assertEqual(result['screenshot'],'not_tested')
        self.assertIn(json.dumps(APP),FakeClient.code)
        self.assertIn("state.text.split('\\n')",FakeClient.code)
        self.assertIn('await sky.click',FakeClient.code)
        self.assertNotIn('calculator',FakeClient.code)
    def test_no_clicks_cannot_pass(self):
        self.assertEqual(self.run_evidence(dict(doctor_runtime=True,state='passed',phase='read_result',nonce=NONCE,clicks=0))['state'],'failed')
    def test_wrong_nonce_rejected(self):
        self.assertEqual(self.run_evidence(dict(doctor_runtime=True,state='passed',phase='read_result',nonce='old',clicks=5))['state'],'failed')
    def test_tool_error_rejected(self):
        self.assertEqual(self.run_evidence(dict(doctor_runtime=True,state='passed',phase='read_result',nonce=NONCE,clicks=5),True)['state'],'failed')
    def test_native_failure_explained(self):
        result=self.run_evidence(dict(doctor_runtime=True,state='failed',phase='native_connection',nonce=NONCE,clicks=0,reason='native_pipe_failed'))
        self.assertEqual(result['state'],'failed');self.assertIn('未執行點擊',result['detail'])
    def test_invalid_batch_not_started(self):
        with patch.object(r,'Client',FakeClient), self.assertRaises(ValueError):r.verify_node(Path('/tmp'),"';bad")
    def test_foreign_phase_rejected(self):
        self.assertEqual(self.run_evidence(dict(doctor_runtime=True,state='passed',phase='unknown',nonce=NONCE,clicks=5))['state'],'failed')

class FakeNative:
    wrong_batch=False; wrong_result=False; duplicate=False; fail_click=False
    records=[]; closed=False
    def __init__(self,home):self.clicks=0;FakeNative.records=[];FakeNative.closed=False
    def initialize(self):return {'tools':[{'name':'get_app_state','inputSchema':{'properties':{'app':{'type':'string'}}}}, {'name':'click','inputSchema':{'properties':{'app':{'type':'string'},'element_index':{'type':'string'}}}}]}
    def call(self,name,args):
        FakeNative.records.append((name,args))
        if name=='click':
            if FakeNative.fail_click:raise r.RuntimeErrorSafe('known_test_failure')
            self.clicks+=1
            return {'content':[]}
        nonce='old' if FakeNative.wrong_batch else NONCE
        text=f'0 standard window Doctor\n90 text 實測批次：{nonce}\n91 text 實測算式：1 + 1\n92 text 實測結果：{20 if FakeNative.wrong_result else 2}\n93 text 實測點擊：{self.clicks}\n'
        for index,label in enumerate(['清除','1','加號','等號']):text+=f'{10+self.clicks*10+index} button 實測：{label}\n'
        if FakeNative.duplicate:text+='999 button 實測：清除\n'
        return {'content':[{'type':'text','text':text}]}
    def close(self):FakeNative.closed=True

class NativeTests(unittest.TestCase):
    def setUp(self):
        own=patch.object(r,'own_app',return_value=Path(APP));own.start();self.addCleanup(own.stop)
        FakeNative.wrong_batch=False;FakeNative.wrong_result=False;FakeNative.duplicate=False;FakeNative.fail_click=False
    def run_report(self):
        with patch.object(r,'AppServerClient',FakeNative):result=r.verify_legacy(Path('/tmp'),NONCE)
        self.assertTrue(FakeNative.closed)
        return result
    def test_live_route_contract(self):
        result=self.run_report();self.assertEqual(result['state'],'passed');self.assertEqual(result['clicks'],5)
        clicks=[args['element_index'] for name,args in FakeNative.records if name=='click']
        self.assertEqual(clicks,['10','21','32','41','53'])
        self.assertEqual(len([x for x in FakeNative.records if x[0]=='get_app_state']),6)
        self.assertTrue(all(x[1]['app']==APP for x in FakeNative.records))
        self.assertEqual(result['screenshot'],'not_tested')
    def test_batch_stale(self):
        FakeNative.wrong_batch=True;result=self.run_report();self.assertEqual(result['state'],'failed');self.assertEqual(result['clicks'],0)
    def test_result_twenty_not_two(self):
        FakeNative.wrong_result=True;self.assertEqual(self.run_report()['state'],'failed')
    def test_duplicate_control_no_guess(self):
        FakeNative.duplicate=True;result=self.run_report();self.assertEqual(result['clicks'],0);self.assertEqual(result['state'],'failed')
    def test_click_failure_not_success(self):
        FakeNative.fail_click=True;result=self.run_report();self.assertEqual(result['clicks'],0);self.assertEqual(result['state'],'failed')
    def test_tool_error_is_rejected(self):
        with self.assertRaises(r.RuntimeErrorSafe):r.native_text({'content':[]})
    def test_invalid_batch(self):
        with self.assertRaises(ValueError):r.verify(Path('/tmp'),';bad')
    def test_required_automation_purpose_present(self):
        info=plistlib.loads((Path(__file__).resolve().parents[1]/'Resources/Info.plist').read_bytes())
        self.assertTrue(info.get('NSAppleEventsUsageDescription'))
        self.assertIn('Codex Computer Use',info['NSAppleEventsUsageDescription'])
    def test_diff_snapshot_updates_and_removes(self):
        first=r.merge_native_state({},'~\t23 button 實測：清除\n+ 24 button 實測：1\n~ 90 text 實測批次：'+NONCE)
        updated=r.merge_native_state(first,'~ 91 text 實測結果：2\n- 24 button 實測：1')
        self.assertIn('23',updated);self.assertNotIn('24',updated)
        self.assertIn('實測結果：2',r.state_text(updated))
    def test_full_snapshot_discards_stale_controls(self):
        self.assertNotIn('23',r.merge_native_state({'23':'button old'},'0 standard window Doctor\n24 button new'))
    def test_diff_with_window_header_keeps_unchanged_controls(self):
        self.assertIn('23',r.merge_native_state({'23':'button test'},'0 standard window Doctor\n~27 text new result'))
    def test_indented_change_marker(self):
        self.assertEqual(r.merge_native_state({'27':'text old'},'\t\t~27 text new')['27'],'text new')
    def test_hosted_node_does_not_require_unused_legacy_server(self):
        config={'mcp_servers':{'node_repl':{'command':str(r.RUNTIME/'bin/node_repl'),'args':[],'env':{}},'computer-use':{'enabled':False}}}
        with patch.object(r,'node_command',return_value=Path('/fixture/node_repl')),patch.object(r.b,'config_data',return_value=config),patch.object(r.AppServerClient,'__init__',return_value=None) as parent:
            r.HostedNodeClient(Path('/tmp'))
            parent.assert_called_once_with(Path('/tmp'),require_native=False)
    def test_hosted_node_rejects_unknown_launcher(self):
        with patch.object(r.b,'config_data',return_value={'mcp_servers':{'node_repl':{'command':'unknown'}}}), self.assertRaises(r.RuntimeErrorSafe):
            r.HostedNodeClient(Path('/tmp'))

if __name__=='__main__':unittest.main()
