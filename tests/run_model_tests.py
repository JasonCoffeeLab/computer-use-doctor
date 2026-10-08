"""Compile isolated native model smoke. Never targets the user's configuration."""
import tempfile,subprocess,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from test_backend import plugin
with tempfile.TemporaryDirectory(prefix='doctor-v9-fixture-',dir='/private/tmp') as folder:
    home=Path(folder)
    plugin(home/'.tmp/bundled-marketplaces/openai-bundled/plugins/browser')
    (home/'config.toml').write_text('[plugins."browser@openai-bundled"]\nenabled=true\n')
    app=home/'Smoke.app/Contents'
    (app/'MacOS').mkdir(parents=True)
    shutil.copytree(ROOT/'Resources',app/'Resources')
    binary=app/'MacOS/Smoke'
    subprocess.run(['xcrun','swiftc','-D','TESTING','-parse-as-library','-module-cache-path',str(home/'module-cache'),str(ROOT/'Sources/main.swift'),str(ROOT/'tests/MonitorSmoke.swift'),'-o',str(binary)],check=True)
    subprocess.run([str(binary),'--fixture','--home',str(home)],check=True,timeout=60)
