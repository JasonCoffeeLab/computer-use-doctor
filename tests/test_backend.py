import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Resources'))
import backend as b


def plugin(path,name='browser',version='1.10.0'):
    (path/'.codex-plugin').mkdir(parents=True)
    (path/'.codex-plugin/plugin.json').write_text(json.dumps(dict(name=name,version=version,skills='./skills/')))
    (path/'skills').mkdir();(path/'skills/SKILL.md').write_text('Synthetic fixture')
    (path/'runtime').mkdir();(path/'runtime/helper').write_bytes(b'helper');(path/'runtime/helper').chmod(0o700)


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='doctor-v3-test-');self.addCleanup(self.tmp.cleanup)
        self.home=Path(self.tmp.name)
        self.source=self.home/'.tmp/bundled-marketplaces/openai-bundled/plugins/browser'
        plugin(self.source)
        self.config=self.home/'config.toml'
        self.original=b'service_tier = "default"\nmodel = "keep"\napproval_policy = "on-request"\n[plugins."browser@openai-bundled"]\nenabled = true\n'
        self.config.write_bytes(self.original)
        self.base=self.home/'plugins/cache/openai-bundled/browser'
        self.target=self.base/'1.10.0'

    def plan(self):return b.plugin_diagnostics(self.home)[2]
    def repair(self):return b.repair(self.home,self.plan(),True)

    def test_readonly_no_mutations(self):
        before=b.fingerprint(self.home)
        d=b.diagnose(self.home,False)
        self.assertEqual(before,b.fingerprint(self.home));self.assertEqual(d['repair_count'],1)

    def binding_fixture(self):
        stub=dict(mcpServers=dict(cua_repl=dict(command='node',enabled=False,args=[])))
        (self.source/'.mcp.json').write_text(json.dumps(stub))
        shutil.copytree(self.source,self.target)
        runtime=self.home/'ChatGPT.app/Contents/Resources/cua_node'
        (runtime/'bin').mkdir(parents=True);node=runtime/'bin/node';node.write_text('fixture');node.chmod(0o700)
        package=runtime/'lib/node_modules/@oai/cua-repl';(package/'bin').mkdir(parents=True)
        entry=package/'bin/cua-repl.mjs';entry.write_text('fixture')
        (package/'package.json').write_text(json.dumps(dict(name='@oai/cua-repl',bin={'cua-repl':'bin/cua-repl.mjs'})))
        material=dict(mcpServers=dict(cua_repl=dict(command=str(node),enabled=True,args=[str(entry)],env={'FIXTURE':'yes'},env_vars=[])))
        (self.target/'.mcp.json').write_text(json.dumps(material))
        return runtime

    def test_binding_confirmed_without_overwriting_mcp(self):
        self.binding_fixture();(self.base/'latest').symlink_to(self.target.name)
        before=b.fingerprint(self.target)
        row=b.diagnose(self.home,False)['plugins'][0]
        self.assertEqual(row['state'],'configured');self.assertFalse(row['repairable'])
        self.assertEqual(before,b.fingerprint(self.target))

    def test_binding_link_repair_preserves_materialized_config(self):
        self.binding_fixture();before=b.fingerprint(self.target)
        row=b.diagnose(self.home,False)['plugins'][0];self.assertTrue(row['repairable'])
        result=self.repair()
        self.assertEqual(before,b.fingerprint(self.target))
        self.assertEqual(result['diagnostic']['plugins'][0]['state'],'configured')

    def test_binding_missing_entry_stays_unconfirmed(self):
        runtime=self.binding_fixture()
        (runtime/'lib/node_modules/@oai/cua-repl/bin/cua-repl.mjs').unlink()
        row=b.diagnose(self.home,False)['plugins'][0]
        self.assertEqual(row['state'],'unknown');self.assertFalse(row['repairable'])

    def test_binding_payload_corruption_not_hidden(self):
        self.binding_fixture();(self.target/'runtime/helper').write_bytes(b'broken')
        self.assertEqual(b.diagnose(self.home,False)['plugins'][0]['state'],'unknown')

    def test_disabled_tool_classified_without_enabling(self):
        self.config.write_text('[mcp_servers.computer-use]\nenabled=false\ncommand="node"\n')
        before=self.config.read_bytes();rows=b.mcp_diagnostics(self.home)
        self.assertEqual(rows[0]['state'],'disabled');self.assertEqual(before,self.config.read_bytes())

    def test_compact_blocked_summary_stops_automation(self):
        d=b.diagnose(self.home,False)
        compact={k:d[k] for k in ('repair_count','plan_id','approval_sources')}
        compact['transaction_blocked']=True
        self.assertTrue(b.auto_decision(compact,d['plan_id'],d['approval_sources'],[])['pause'])

    def test_pending_transaction_visible_in_diagnostic(self):
        self.repair()
        receipt=self.home/'computer-use-doctor-v3/receipts'/('a'*32+'.json')
        b.atomic_json(receipt,dict(transaction='a'*32,status='prepared',created_at='',receipts=[]))
        d=b.diagnose(self.home,False)
        self.assertEqual(d['repair_count'],0)
        self.assertTrue(any(row['status']=='prepared' for row in d['transaction_history']))
        gate=b.auto_decision(d,d['plan_id'],d['approval_sources'],[])
        self.assertFalse(gate['eligible']);self.assertTrue(gate['pause'])

    def test_enabled_scope_change_pauses_auto(self):
        self.config.write_text('[plugins."browser@openai-bundled"]\nenabled=false\n')
        initial=b.diagnose(self.home,False)
        self.config.write_bytes(self.original)
        current=b.diagnose(self.home,False)
        self.assertNotEqual(initial['approval_sources'],current['approval_sources'])
        gate=b.auto_decision(current,current['plan_id'],initial['approval_sources'],[])
        self.assertFalse(gate['eligible']);self.assertEqual(gate['code'],'scope_changed')

    def test_scope_change_pauses_even_with_no_fault(self):
        initial=b.diagnose(self.home,False)
        self.config.write_text('[plugins."browser@openai-bundled"]\nenabled=false\n')
        current=b.diagnose(self.home,False)
        self.assertEqual(current['repair_count'],0)
        self.assertTrue(b.auto_decision(current,current['plan_id'],initial['approval_sources'],[])['pause'])

    def test_disabled_source_update_does_not_pause_confirmed_scope(self):
        initial=b.diagnose(self.home,False)
        other=self.source.parent/'chrome'
        plugin(other,name='chrome',version='2.0.0')
        current=b.diagnose(self.home,False)
        self.assertTrue(b.auto_decision(current,current['plan_id'],initial['approval_sources'],[])['eligible'])

    def test_post_repair_snapshot_explicitly_unprobed(self):
        d=self.repair()['diagnostic']
        self.assertFalse(d['probes_completed'])
        self.assertEqual(d['network'],[])

    def test_full_recheck_restores_browser_network_scope(self):
        result=self.repair()
        with patch.object(b,'browser_diagnostics',return_value=[dict(name='browser',state='checked',detail='fixture')]):
            d=b.diagnose(self.home,True)
        self.assertFalse(result['diagnostic']['probes_completed'])
        self.assertTrue(d['probes_completed']);self.assertEqual(len(d['browser']),1)
        self.assertEqual(d['network'],[]);self.assertFalse(hasattr(b,'network_diagnostics'))

    def test_event_log_fixed_metadata_and_private_permissions(self):
        before=self.config.read_bytes()
        result=b.record_event(self.home,dict(action='diagnose',code='returned'))
        self.assertEqual(set(result['events'][0]),{'created_at','action','code'})
        path=self.home/'computer-use-doctor-v3/events-v6.json'
        self.assertEqual(path.stat().st_mode & 0o777,0o600)
        self.assertEqual(self.config.read_bytes(),before)

    def test_event_log_refuses_raw_input(self):
        with self.assertRaises(ValueError):b.record_event(self.home,dict(action='classify',code='returned',text='SECRET'))
        self.assertFalse((self.home/'computer-use-doctor-v3/events-v6.json').exists())

    def test_event_log_corruption_preserved(self):
        b.record_event(self.home,dict(action='diagnose',code='returned'))
        path=self.home/'computer-use-doctor-v3/events-v6.json';path.write_text('broken')
        with self.assertRaises(ValueError):b.record_event(self.home,dict(action='diagnose',code='returned'))
        self.assertEqual(path.read_text(),'broken')

    def test_event_log_symlink_refused(self):
        b.record_event(self.home,dict(action='diagnose',code='returned'))
        path=self.home/'computer-use-doctor-v3/events-v6.json';saved=self.home/'saved.json'
        path.rename(saved);path.symlink_to(saved)
        with self.assertRaises(ValueError):b.record_event(self.home,dict(action='diagnose',code='returned'))

    def test_event_history_readonly(self):
        before=b.fingerprint(self.home)
        self.assertEqual(b.event_history(self.home)['events'],[])
        self.assertEqual(b.fingerprint(self.home),before)

    def test_event_retention_does_not_trim_transactions(self):
        result=self.repair()
        for _ in range(202):b.record_event(self.home,dict(action='auto-decision',code='waiting'))
        self.assertEqual(len(b.event_history(self.home)['events']),200)
        self.assertEqual(b.history(self.home)['transactions'][0]['transaction'],result['transaction'])

    def test_same_size_content_corruption_detected(self):
        shutil.copytree(self.source,self.target);(self.base/'latest').symlink_to(self.target.name)
        (self.target/'runtime/helper').write_bytes(b'broken')
        self.assertEqual(b.diagnose(self.home,False)['repair_count'],1)
        self.assertEqual(self.repair()['diagnostic']['repair_count'],0)

    def test_receipt_wrong_identity_is_unreadable(self):
        result=self.repair()
        receipt=self.home/'computer-use-doctor-v3/receipts'/(result['transaction']+'.json')
        data=json.loads(receipt.read_text());data['transaction']=None;receipt.write_text(json.dumps(data))
        self.assertEqual(b.history(self.home)['transactions'][0]['status'],'unreadable')

    def test_receipt_bad_step_is_unreadable(self):
        result=self.repair()
        receipt=self.home/'computer-use-doctor-v3/receipts'/(result['transaction']+'.json')
        data=json.loads(receipt.read_text());data['receipts'][0]['phase']=[];receipt.write_text(json.dumps(data))
        self.assertEqual(b.history(self.home)['transactions'][0]['status'],'unreadable')

    def test_restore_blocks_other_pending_transaction(self):
        result=self.repair()
        extra=self.home/'computer-use-doctor-v3/receipts'/('f'*32+'.json')
        extra.write_text(json.dumps(dict(transaction='f'*32,status='prepared',receipts=[],created_at='')))
        before=b.fingerprint(self.target)
        with self.assertRaises(ValueError):b.restore(self.home,result['transaction'],True)
        self.assertEqual(before,b.fingerprint(self.target))

    def test_receipt_symlink_not_read(self):
        result=self.repair()
        receipt=self.home/'computer-use-doctor-v3/receipts'/(result['transaction']+'.json')
        saved=self.home/'fixture-receipt.json';receipt.rename(saved);receipt.symlink_to(saved)
        self.assertEqual(b.history(self.home)['transactions'][0]['status'],'unreadable')

    def test_missing_source_is_unknown(self):
        shutil.rmtree(self.source)
        row=b.diagnose(self.home,False)['plugins'][0]
        self.assertEqual(row['state'],'unknown');self.assertFalse(row['repairable'])

    def test_disabled_no_enable(self):
        self.config.write_text('[plugins."browser@openai-bundled"]\nenabled=false\n')
        self.assertEqual(b.diagnose(self.home,False)['repair_count'],0)

    def test_complete_cache_structure_only(self):
        shutil.copytree(self.source,self.target);(self.base/'latest').symlink_to(self.target.name)
        row=b.diagnose(self.home,False)['plugins'][0]
        self.assertEqual(row['state'],'checked');self.assertFalse(row['repairable'])

    def test_invalid_toml_refuses(self):
        self.config.write_text('[plugins broken')
        with self.assertRaises(ValueError):b.diagnose(self.home,False)

    def test_toml_single_quotes_inline(self):
        self.config.write_text("plugins = { 'browser@openai-bundled' = { enabled = true } }\n")
        self.assertEqual(b.diagnose(self.home,False)['repair_count'],1)

    def test_confirmation_before_writes(self):
        before=b.fingerprint(self.home)
        with self.assertRaises(ValueError):b.repair(self.home,self.plan(),False)
        self.assertEqual(before,b.fingerprint(self.home))

    def test_stale_plan_rejected(self):
        plan=self.plan();self.config.write_bytes(self.original+b'\n# changed\n')
        with self.assertRaises(ValueError):b.repair(self.home,plan,True)
        self.assertFalse(self.target.exists())

    def test_config_and_service_unchanged(self):
        result=self.repair()
        self.assertEqual(result['repaired'],1);self.assertEqual(self.config.read_bytes(),self.original)
        self.assertEqual((self.base/'latest').resolve(),self.target.resolve())
        self.assertEqual(result['diagnostic']['repair_count'],0)

    def test_missing_target_restore_retains_new_cache(self):
        result=self.repair();b.restore(self.home,result['transaction'],True)
        self.assertFalse((self.base/'latest').exists());self.assertTrue(self.target.exists())

    def test_incomplete_cache_restored(self):
        shutil.copytree(self.source,self.target);(self.target/'runtime/helper').write_bytes(b'x')
        old=b.fingerprint(self.target)
        result=self.repair();b.restore(self.home,result['transaction'],True)
        self.assertEqual(b.fingerprint(self.target),old)

    def test_real_latest_directory_restored(self):
        (self.base/'latest').mkdir(parents=True);(self.base/'latest/data').write_bytes(b'original')
        result=self.repair();b.restore(self.home,result['transaction'],True)
        self.assertFalse((self.base/'latest').is_symlink())
        self.assertEqual((self.base/'latest/data').read_bytes(),b'original')

    def test_old_symlink_restored(self):
        self.base.mkdir(parents=True);(self.base/'latest').symlink_to('old-version')
        result=self.repair();b.restore(self.home,result['transaction'],True)
        self.assertEqual(os.readlink(self.base/'latest'),'old-version')

    def test_restore_rejects_new_content(self):
        result=self.repair();(self.target/'runtime/helper').write_bytes(b'new external content')
        with self.assertRaises(ValueError):b.restore(self.home,result['transaction'],True)
        self.assertEqual((self.target/'runtime/helper').read_bytes(),b'new external content')

    def test_restore_confirmation(self):
        result=self.repair()
        with self.assertRaises(ValueError):b.restore(self.home,result['transaction'],False)
        self.assertTrue((self.base/'latest').is_symlink())

    def test_lock_rejects_concurrent_mutation(self):
        plan=self.plan()
        with b.mutation_lock(self.home):
            with self.assertRaises(ValueError):b.repair(self.home,plan,True)

    def test_source_changed_after_plan(self):
        plan=self.plan();(self.source/'runtime/helper').write_bytes(b'changed')
        with self.assertRaises(ValueError):b.repair(self.home,plan,True)

    def test_failure_journal_records_current_item(self):
        original=b.os.replace
        def fail(source,target):
            if Path(source).name.startswith('.doctor-stage-'):raise OSError('synthetic failure')
            return original(source,target)
        with patch.object(b.os,'replace',fail):
            with self.assertRaises(OSError):self.repair()
        data=json.loads(next((self.home/'computer-use-doctor-v3/receipts').glob('*.json')).read_text())
        self.assertEqual(data['status'],'partial_or_failed');self.assertEqual(data['receipts'][0]['phase'],'needs_review')
        with self.assertRaises(ValueError):self.repair()

    def test_failed_restore_directory_keeps_repaired_link(self):
        (self.base/'latest').mkdir(parents=True);(self.base/'latest/data').write_bytes(b'old')
        result=self.repair();original=b.os.replace
        def fail(source,target):
            if Path(source).name.startswith('latest.bak-doctor-'):raise OSError('synthetic failure')
            return original(source,target)
        with patch.object(b.os,'replace',fail):
            with self.assertRaises(OSError):b.restore(self.home,result['transaction'],True)
        self.assertEqual((self.base/'latest').resolve(),self.target.resolve())
        self.assertEqual(b.history(self.home)['transactions'][0]['status'],'restore_partial_or_failed')

    def test_receipt_target_tamper_refused(self):
        result=self.repair();receipt=self.home/'computer-use-doctor-v3/receipts'/(result['transaction']+'.json')
        data=json.loads(receipt.read_text());data['receipts'][0]['target']=str(self.home/'unrelated')
        receipt.write_text(json.dumps(data))
        with self.assertRaises(ValueError):b.restore(self.home,result['transaction'],True)

    def test_cache_symlink_escape_not_repairable(self):
        outside=Path(tempfile.mkdtemp(prefix='doctor-v3-outside-'));self.addCleanup(shutil.rmtree,outside)
        (self.home/'plugins/cache/openai-bundled').mkdir(parents=True)
        self.base.symlink_to(outside,target_is_directory=True)
        self.assertFalse(b.diagnose(self.home,False)['plugins'][0]['repairable'])

    def test_mcp_does_not_run_commands(self):
        self.config.write_text('[mcp_servers.test]\ncommand="/definitely/missing"\n')
        row=b.mcp_diagnostics(self.home)[0];self.assertEqual(row['state'],'warning')

    def test_materialized_mcp_not_overwritten(self):
        (self.source/'.mcp.json').write_text('{"mcpServers":{"server":{"command":"source"}}}')
        shutil.copytree(self.source,self.target)
        (self.target/'.mcp.json').write_text('{"mcpServers":{"server":{"command":"materialized"}}}')
        row=b.diagnose(self.home,False)['plugins'][0]
        self.assertEqual(row['state'],'unknown');self.assertFalse(row['repairable'])

    def test_classifier_local_candidates(self):
        result=b.classify('Cloud browser is not permitted on https://example.com')
        self.assertEqual(result['matches'][0]['kind'],'website_policy')
        self.assertNotIn('example.com',json.dumps(result))

    def test_classifier_unknown(self):self.assertEqual(b.classify('ordinary note')['matches'],[])

    def test_redact(self):self.assertNotIn('SECRET',b.redact('https://user:SECRET@example.com token=SECRET'))

    def test_cli_json(self):
        result=subprocess.run(['/usr/bin/python3',str(ROOT/'Resources/backend.py'),'diagnose','--home',str(self.home),'--no-probe'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr);self.assertTrue(json.loads(result.stdout)['ok'])

    def test_cli_parse_error_safe(self):
        self.config.write_text('token="SECRET"\n[broken')
        result=subprocess.run(['/usr/bin/python3',str(ROOT/'Resources/backend.py'),'diagnose','--home',str(self.home),'--no-probe'],capture_output=True,text=True)
        self.assertEqual(result.returncode,1);self.assertNotIn('SECRET',result.stdout+result.stderr)

    def test_backup_content_tamper_refused(self):
        shutil.copytree(self.source,self.target);(self.target/'runtime/helper').write_bytes(b'old')
        result=self.repair();receipt=self.home/'computer-use-doctor-v3/receipts'/(result['transaction']+'.json')
        record=json.loads(receipt.read_text());backup=Path(record['receipts'][0]['original'])
        (backup/'runtime/helper').write_bytes(b'tampered')
        current=b.fingerprint(self.target)
        with self.assertRaises(ValueError):b.restore(self.home,result['transaction'],True)
        self.assertEqual(b.fingerprint(self.target),current)

    def test_invalid_receipt_blocks_repair(self):
        directory=self.home/'computer-use-doctor-v3/receipts';directory.mkdir(parents=True)
        (directory/('a'*32+'.json')).write_text('{broken')
        self.assertEqual(b.history(self.home)['transactions'][0]['status'],'unreadable')
        with self.assertRaises(ValueError):self.repair()
        self.assertFalse(self.target.exists())

    def test_mcp_wrong_command_type_not_global_failure(self):
        self.config.write_text('[mcp_servers.test]\ncommand=123\n')
        self.assertEqual(b.mcp_diagnostics(self.home)[0]['state'],'unknown')

    def test_invalid_version_does_not_break_report(self):
        p=self.source/'.codex-plugin/plugin.json';data=json.loads(p.read_text());data['version']=123;p.write_text(json.dumps(data))
        d=b.diagnose(self.home,False)
        self.assertIsInstance(d['plugins'][0]['version'],str);self.assertIsNone(d['approval_sources']['browser']['version'])

    def test_auto_needs_two_stable_observations(self):
        current=b.diagnose(self.home,False)
        self.assertFalse(b.auto_decision(current,None,current['approval_sources'],[])['eligible'])
        self.assertTrue(b.auto_decision(current,current['plan_id'],current['approval_sources'],[])['eligible'])

    def test_auto_source_change_refuses(self):
        current=b.diagnose(self.home,False)
        self.assertFalse(b.auto_decision(current,current['plan_id'],{},[])['eligible'])

    def test_auto_no_repeat(self):
        current=b.diagnose(self.home,False)
        self.assertFalse(b.auto_decision(current,current['plan_id'],current['approval_sources'],[current['plan_id']])['eligible'])

    def test_auto_cooldown(self):
        current=b.diagnose(self.home,False)
        self.assertFalse(b.auto_decision(current,current['plan_id'],current['approval_sources'],[],True)['eligible'])

    def test_auto_no_known_fault(self):
        current=b.diagnose(self.home,False);current['repair_count']=0
        self.assertFalse(b.auto_decision(current,current['plan_id'],current['approval_sources'],[])['eligible'])

    def test_auto_transition_repair_and_recheck(self):
        initial=b.diagnose(self.home,False);baseline=initial['approval_sources']
        self.assertFalse(b.auto_decision(initial,None,baseline,[])['eligible'])
        current=b.diagnose(self.home,False)
        self.assertTrue(b.auto_decision(current,initial['plan_id'],baseline,[])['eligible'])
        result=b.repair(self.home,current['plan_id'],True)
        self.assertEqual(result['diagnostic']['repair_count'],0)
        self.assertFalse(b.auto_decision(result['diagnostic'],current['plan_id'],baseline,[current['plan_id']])['eligible'])
        self.assertEqual(self.config.read_bytes(),self.original)

    def test_auto_decision_cli_no_mutation(self):
        current=b.diagnose(self.home,False);before=b.fingerprint(self.home)
        request=dict(current=current,previous_plan=current['plan_id'],approved_sources=current['approval_sources'],attempted_plans=[])
        result=subprocess.run(['/usr/bin/python3',str(ROOT/'Resources/backend.py'),'auto-decision','--home',str(self.home)],input=json.dumps(request),text=True,capture_output=True)
        self.assertEqual(result.returncode,0);self.assertTrue(json.loads(result.stdout)['data']['eligible'])
        self.assertEqual(before,b.fingerprint(self.home))


if __name__=='__main__':unittest.main(verbosity=2)
