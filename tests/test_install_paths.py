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

if __name__=='__main__':unittest.main()
