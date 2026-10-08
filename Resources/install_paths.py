"""Read-only discovery. Installation layout checks are not publisher verification."""
import os
import plistlib
import shutil
from pathlib import Path

BUNDLE_ID = 'org.computer-use-doctor.preview.v9'

def config_home(explicit=None, environment=None, user_home=None):
    environment = os.environ if environment is None else environment
    user_home = Path.home() if user_home is None else Path(user_home)
    raw = explicit if explicit is not None else environment.get('CODEX_HOME')
    source = 'App 選擇／明確指定' if explicit is not None else 'CODEX_HOME' if raw is not None else '預設位置'
    if raw is None:
        candidate = user_home / '.codex'
    else:
        if not str(raw).strip():
            raise ValueError('指定設定目錄為空，未退回其他設定；請選擇自己的 Codex 設定資料夾。')
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            raise ValueError('設定目錄必須是絕對路徑；未依工作目錄猜測，也未退回其他設定。')
    candidate = candidate.resolve()
    if candidate in (Path('/'), user_home.resolve()):
        raise ValueError('不可將整個家目錄或系統根目錄當成修復環境。')
    if not candidate.is_dir():
        raise ValueError('指定 Codex 設定目錄不存在或不是資料夾；請在 App 選擇既有設定目錄，不自動建立或退回另一份設定。')
    return candidate, source

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
    roots = [(home / 'packages/standalone').resolve(),(user_home / '.codex/packages/standalone').resolve()]
    candidates = [root / 'current/bin/codex' for root in roots]+[user_home / '.local/bin/codex']
    found = shutil.which('codex')
    if found:
        candidates.append(Path(found))
    for candidate in candidates:
        resolved = candidate.resolve()
        if not any(resolved.is_relative_to(root) for root in roots):continue
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
