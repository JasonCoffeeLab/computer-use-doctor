import os,plistlib,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Resources'))
import install_paths as p

class InstallPathTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
    def executable(self,path):
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text('fixture, never executed');path.chmod(0o700);return path
    def test_other_user_standalone(self):
        home=self.root/'another user/.codex'
        cli=self.executable(home/'packages/standalone/current/bin/codex')
        self.assertEqual(p.codex_cli(home,self.root/'another user'),cli.resolve())
    def test_symlink_to_outside_rejected(self):
        home=self.root/'.codex';link=home/'packages/standalone/current/bin/codex'
        outside=self.executable(self.root/'outside/codex');link.parent.mkdir(parents=True);link.symlink_to(outside)
        with patch.object(p.shutil,'which',return_value=str(outside)),self.assertRaises(ValueError):p.codex_cli(home,self.root)
    def test_path_unknown_command_rejected(self):
        cli=self.executable(self.root/'unknown/codex')
        with patch.object(p.shutil,'which',return_value=str(cli)),self.assertRaises(ValueError):p.codex_cli(self.root/'.codex',self.root)
    def test_missing_cli_has_actionable_message(self):
        with patch.object(p.shutil,'which',return_value=None),self.assertRaisesRegex(ValueError,'standalone'):p.codex_cli(self.root/'.codex',self.root)
    def bundle(self):
        app=self.root/'Folder with spaces/Doctor Preview.app';resources=app/'Contents/Resources';resources.mkdir(parents=True)
        (app/'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier':p.BUNDLE_ID,'CFBundleExecutable':'ComputerUseDoctor'}))
        self.executable(app/'Contents/MacOS/ComputerUseDoctor');return app,resources
    def test_own_bundle_at_nonpersonal_path(self):
        app,resources=self.bundle()
        with patch.object(p,'__file__',str(resources/'install_paths.py')):self.assertEqual(p.own_app(app),app.resolve())
    def test_foreign_bundle_rejected_before_operations(self):
        app,resources=self.bundle()
        with patch.object(p,'__file__',str(resources/'install_paths.py')),self.assertRaises(ValueError):p.own_app(self.root/'Other.app')
    def test_wrong_bundle_id_rejected(self):
        app,resources=self.bundle();(app/'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier':'other'}))
        with patch.object(p,'__file__',str(resources/'install_paths.py')),self.assertRaises(ValueError):p.own_app(app)
    def test_unknown_node_command_rejected(self):
        with self.assertRaises(ValueError):p.node_command('/tmp/unknown/node_repl')
    def test_explicit_home_wins_over_environment(self):
        chosen=self.root/'selected';chosen.mkdir()
        result,source=p.config_home(chosen,{'CODEX_HOME':'/missing'},self.root)
        self.assertEqual(result,chosen.resolve());self.assertIn('明確指定',source)
    def test_environment_home_used(self):
        chosen=self.root/'custom home';chosen.mkdir()
        self.assertEqual(p.config_home(None,{'CODEX_HOME':str(chosen)},self.root)[0],chosen.resolve())
    def test_default_only_when_override_absent(self):
        default=self.root/'.codex';default.mkdir()
        self.assertEqual(p.config_home(None,{},self.root),(default.resolve(),'預設位置'))
    def test_invalid_override_never_falls_back(self):
        (self.root/'.codex').mkdir()
        for value in ('','relative','.','/missing-doctor-fixture',str(self.root)):
            with self.subTest(value=value),self.assertRaises(ValueError):p.config_home(None,{'CODEX_HOME':value},self.root)
    def test_file_not_config_directory(self):
        f=self.root/'file';f.write_text('fixture')
        with self.assertRaises(ValueError):p.config_home(f,{},self.root)
    def test_custom_config_keeps_default_distribution_separate(self):
        chosen=self.root/'custom config';chosen.mkdir()
        cli=self.executable(self.root/'.codex/packages/standalone/current/bin/codex')
        self.assertEqual(p.codex_cli(chosen,self.root),cli.resolve())

if __name__=='__main__':unittest.main()
