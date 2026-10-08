"""Read-only discovery. Installation layout checks are not publisher verification."""
import os
import plistlib
import shutil
from pathlib import Path

BUNDLE_ID = 'org.computer-use-doctor.preview.v9'

def own_app(app_path=None):
    resources = Path(__file__).resolve().parent
    app = Path(app_path).resolve() if app_path else resources.parent.parent
    if app.suffix != '.app' or resources != app / 'Contents/Resources':
        raise ValueError('只能實測正在執行的 Doctor 自身；目標與本次內置程式不匹配。')
    try:
        info = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
        executable = app / 'Contents/MacOS/ComputerUseDoctor'
        if info.get('CFBundleIdentifier') != BUNDLE_ID or info.get('CFBundleExecutable') != 'ComputerUseDoctor' or not executable.is_file():
            raise ValueError('Doctor App 身份或執行檔未匹配。')
    except OSError:
        raise ValueError('未取得完整 Doctor App；請從已建置的 App 進行實測。')
    return app

def codex_cli(home, user_home=None):
    """Preview supports the desktop-managed standalone distribution only."""
    home = Path(home).resolve()
    user_home = Path(user_home) if user_home else Path.home()
    root = (home / 'packages/standalone').resolve()
    candidates = [home / 'packages/standalone/current/bin/codex', user_home / '.local/bin/codex']
    found = shutil.which('codex')
    if found:
        candidates.append(Path(found))
    for candidate in candidates:
        resolved = candidate.resolve()
        try:
            resolved.relative_to(root)
        except ValueError:
            continue
        if resolved.name == 'codex' and resolved.is_file() and os.access(resolved, os.X_OK):
            return resolved
    raise ValueError('未找到支援的 Codex 桌面版 standalone CLI。Preview 尚未驗證 npm／Homebrew 安裝；不自動安裝或執行其他命令。')

def node_command(command):
    if not isinstance(command, str):
        raise ValueError('未取得 node_repl 絕對路徑；請先在官方 App 設定啟用 Computer Use。')
    candidate = Path(command)
    roots = [Path('/Applications'), Path.home() / 'Applications']
    allowed = [root / name / 'Contents/Resources/cua_node/bin/node_repl'
               for root in roots for name in ('ChatGPT.app', 'Codex.app')]
    if not candidate.is_absolute() or candidate.resolve() not in [p.resolve() for p in allowed] or not candidate.is_file() or not os.access(candidate, os.X_OK):
        raise ValueError('node_repl 不在支援的官方 App 安裝位置，或執行檔不可用；未執行未知配置命令。')
    return candidate
