"""Read-only first-use checks; never installs tools or reads credentials."""
import os,platform,sys
from pathlib import Path
from install_paths import codex_cli,node_command

def inspect_environment(home, source, config_loader, app_path=None):
    rows=[]
    def row(name,passed,detail):
        rows.append(dict(name=name,state='checked' if passed else 'warning',detail=detail))
    config_ready=False;node_ready=False;cli_ready=False
    row('設定目錄',True,'正在使用：'+str(home)+'；來源：'+source+'。未讀取登入憑證。')
    try:
        if not (home/'config.toml').is_file():
            raise ValueError('此目錄沒有 config.toml。請先在官方 App 完成設定，或選擇正確設定資料夾；未生成配置。')
        if (home/'config.toml').is_symlink():
            raise ValueError('配置是符號連結，修復範圍尚未確認；未改動或跟隨它修復。')
        config=config_loader(home)
        config_ready=True
        row('設定檔',True,'config.toml 可解析；沒有讀取 auth.json 或要求密碼。')
    except (ValueError,OSError):
        config={}
        row('設定檔',False,'config.toml 缺少、格式錯誤或為符號連結。請在官方 App 核對，或選擇正確既有目錄；不把它當成可修快取問題。')
    try:
        codex_cli(home)
        cli_ready=True
        row('Codex 執行工具',True,'已找到支援的桌面版 standalone CLI；尚未啟動。')
    except (ValueError,OSError):
        row('Codex 執行工具',False,'未找到支援的 standalone CLI。請先在官方桌面 App 核對安裝；npm／Homebrew 目前未驗證，不自動安裝。')
    try:
        node=config.get('mcp_servers',{}).get('node_repl',{})
        node_command(node.get('command'))
        if node.get('enabled') is False or node.get('args',[])!=[]:
            raise ValueError('停用或不匹配')
        # Validate the environment contract without printing any values.
        from runtime_client import PUBLIC_ENV
        env=node.get('env',{})
        if not isinstance(env,dict) or set(env)-PUBLIC_ENV or any(not isinstance(v,str) for v in env.values()):
            raise ValueError('環境契約不匹配')
        node_ready=True
        row('Computer Use 入口',True,'已找到啟用且契約匹配的 node_repl；實際登入與操作仍須本次實測。')
    except (ValueError,OSError,TypeError):
        row('Computer Use 入口',False,'node_repl 缺少、停用或契約不匹配。請在官方 App 啟用／核對 Computer Use，不貼入別人的設定，也不自動改權限。')
    version=platform.mac_ver()[0].split('.')
    supported=platform.system()=='Darwin' and platform.machine()=='arm64' and bool(version[0]) and int(version[0])>=14
    row('Mac 相容性',supported,'目前預覽支援 Apple Silicon 與 macOS 14+；不把其他平台當成已驗證。')
    python_ready=sys.version_info>=(3,9)
    row('Python 執行環境',python_ready,'目前 Python '+platform.python_version()+'；需要 3.9+，缺件不自動安裝。')
    installed=False
    if app_path:
        app=Path(app_path).resolve()
        installed=app in [Path('/Applications/Computer Use Doctor V9 Preview.app'),Path.home()/'Applications/Computer Use Doctor V9 Preview.app']
    row('App 安裝位置',installed,'已位於本機 Applications；自啟動需本人選擇並另驗。' if installed else '請將 ZIP 下載到本機，解壓並把 App 放進 Applications。此位置不登記自啟動；人工實測可獨立進行。')
    return dict(home=str(home),home_source=source,config_ready=config_ready,
                runtime_ready=config_ready and cli_ready and node_ready and supported and python_ready,
                rows=rows,boundary='首次使用只讀檢查；檔案可用不等於登入、連接或操作通過。')
