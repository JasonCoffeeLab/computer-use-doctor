import io,os,sys,tempfile,unittest,json,contextlib
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Resources'))
import preflight as p
import backend as b

class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.home=Path(self.temp.name)/'custom';self.home.mkdir()
        (self.home/'config.toml').write_text('fixture')
        self.config={'mcp_servers':{'node_repl':{'command':'/fixture/node_repl','args':[],'env':{}}}}
        for name,value in [('codex_cli',Path('/fixture/codex')),('node_command',Path('/fixture/node_repl'))]:
            mock=patch.object(p,name,return_value=value);mock.start();self.addCleanup(mock.stop)
        for name,value in [('system','Darwin'),('machine','arm64'),('mac_ver',('14.0',('','',''),''))]:
            mock=patch.object(p.platform,name,return_value=value);mock.start();self.addCleanup(mock.stop)
    def inspect(self):return p.inspect_environment(self.home,'明確指定',lambda _:self.config)
    def test_ready_is_not_runtime_pass(self):
        result=self.inspect();self.assertTrue(result['runtime_ready']);self.assertNotIn('passed',json.dumps(result))
    def test_missing_config_blocks_repair_and_runtime(self):
        (self.home/'config.toml').unlink()
        result=self.inspect();self.assertFalse(result['config_ready']);self.assertFalse(result['runtime_ready'])
    def test_symlink_config_blocks_mutation_readiness(self):
        (self.home/'config.toml').unlink();outside=self.home.parent/'elsewhere';outside.write_text('fixture')
        (self.home/'config.toml').symlink_to(outside)
        self.assertFalse(self.inspect()['config_ready'])
    def test_bad_config_message_does_not_expose_input(self):
        def bad(_):raise ValueError('private-error-value')
        result=p.inspect_environment(self.home,'explicit',bad)
        self.assertFalse(result['config_ready']);self.assertNotIn('private-error-value',json.dumps(result))
    def test_disabled_node_is_not_enabled(self):
        self.config['mcp_servers']['node_repl']['enabled']=False
        self.assertFalse(self.inspect()['runtime_ready']);self.assertFalse(self.config['mcp_servers']['node_repl']['enabled'])
    def test_unknown_environment_not_executed(self):
        self.config['mcp_servers']['node_repl']['env']={'UNKNOWN_SECRET':'private-value'}
        result=self.inspect();self.assertFalse(result['runtime_ready']);self.assertNotIn('private-value',json.dumps(result))
    def test_missing_cli_has_next_step(self):
        with patch.object(p,'codex_cli',side_effect=ValueError('missing')):
            result=self.inspect();self.assertTrue(result['config_ready']);self.assertFalse(result['runtime_ready'])
            self.assertTrue(any('官方桌面 App' in x['detail'] for x in result['rows']))
    def test_unsupported_platform_not_green(self):
        with patch.object(p.platform,'machine',return_value='x86_64'):self.assertFalse(self.inspect()['runtime_ready'])
    def test_main_respects_custom_home_without_mutation(self):
        stream=io.StringIO()
        with patch.dict(os.environ,{'CODEX_HOME':str(self.home)}),patch.object(sys,'argv',['backend.py','preflight']),patch.object(b,'config_data',return_value=self.config),contextlib.redirect_stdout(stream):b.main()
        result=json.loads(stream.getvalue())
        self.assertTrue(result['ok']);self.assertEqual(result['data']['home'],str(self.home.resolve()))
        self.assertFalse((self.home/'computer-use-doctor-v3').exists())
    def test_empty_environment_fails_without_diagnosis(self):
        with patch.dict(os.environ,{'CODEX_HOME':''}),patch.object(sys,'argv',['backend.py','diagnose']),patch.object(b,'diagnose') as diagnose,contextlib.redirect_stdout(io.StringIO()),self.assertRaises(SystemExit):b.main()
        diagnose.assert_not_called()
    def test_classification_independent_of_invalid_home(self):
        with patch.dict(os.environ,{'CODEX_HOME':''}),patch.object(sys,'argv',['backend.py','classify']),patch.object(sys,'stdin',io.StringIO('timeout')),contextlib.redirect_stdout(io.StringIO()):b.main()
    def test_platform_warning_not_misclassified_as_permission(self):
        result=b.classify('This application is not supported on this Mac.')
        self.assertTrue(any(row['kind']=='platform_incompatible' for row in result['matches']))
        self.assertFalse(any(row['kind']=='authorization_evidence' for row in result['matches']))

if __name__=='__main__':unittest.main()
