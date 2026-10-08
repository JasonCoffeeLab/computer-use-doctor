# Computer Use Doctor — V9 Public Preview

macOS 本機診斷與有限快取修復 App。不是 OpenAI 官方產品，也不是解除安全限制或代替使用者授權的工具。

目前是公開預覽版，不是穩定版。一般使用者應下載 [Releases 中的 App ZIP](https://github.com/JasonCoffeeLab/computer-use-doctor/releases/tag/v9.0.0-preview.1)；GitHub 自動提供的 Source code ZIP 只有原始碼，不能直接雙擊使用。[GitHub Releases 說明](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases)。

下載入口：[V9 預覽 App ZIP](https://github.com/JasonCoffeeLab/computer-use-doctor/releases/download/v9.0.0-preview.1/Computer-Use-Doctor-V9-Preview-arm64.zip)、[校驗清單](https://github.com/JasonCoffeeLab/computer-use-doctor/releases/download/v9.0.0-preview.1/SHA256SUMS)。請先閱讀下方尚未正式簽署／公證的限制。

## 下載者怎麼使用

1. 先確認 Apple Silicon Mac、macOS 14 或以上，並已安裝、登入自己的官方 Codex／ChatGPT 桌面版及啟用 Computer Use。
2. 下載 `Computer-Use-Doctor-V9-Preview-arm64.zip`，解壓後將 App 放入 `/Applications` 或自己家目錄的 `Applications`。不要在 iCloud、下載暫存或磁碟映像中登記登入自啟動。
3. 開啟 App，按「開始檢查」。程式檢查自己的環境，並透過既有官方工具操作 Doctor 自己的測試面板；成功時應顯示本次 5 次點擊、`1 + 1`、結果 `2`。
4. 有可修復項目時，查看本次範圍後按「修復並核查全部項目」。沒有修復候選也會重新驗證，不把未測試改成成功。
5. 若要開機後使用，在 App 內自行打開「登入 Mac 後啟動」。預覽版首次開啟不替你登記；實際登入啟動仍需在自己的 Mac 驗證。

重要：目前 App 僅本機臨時簽署，未取得 Developer ID 簽署與 Apple 公證。若 macOS 阻擋，不關閉 Gatekeeper，也不要執行解除隔離的指令。等待正式簽署版本，或由具備開發環境的人審閱原始碼並自行建置。這版不能宣稱所有人下載後都可無提示啟動。

詳細：[安裝與操作](docs/INSTALL.md)、[疑難排解](docs/FAQ.md)、[安全及資料範圍](docs/SECURITY.md)、[驗證狀態](docs/VERIFICATION.md)。

## 支援範圍與限制

- 現有環境需有可執行的 `/usr/bin/python3`（3.9+）。沒有時只報告缺件，不自動安裝開發工具。
- 本次預覽只支援桌面版管理的 `.codex/packages/standalone` CLI。npm、Homebrew、Windows、Intel Mac 尚未驗證，不承諾支援。
- 官方 App 支援位置：`/Applications` 或使用者 `Applications`，App 名稱為 `ChatGPT.app`／`Codex.app`。現有設定需提供 `node_repl`；不同工具或契約出現時保留具體缺口，不複製他人的配置。
- App Server 介面及桌面工具會隨官方版本改變。依 [OpenAI 官方 App Server 文件](https://learn.chatgpt.com/docs/app-server) 對接；本工具不建立模型回合、不傳送自訂推理提示，不偽造認證。
- 操作測試只驗證 Doctor 自身，不保證 Safari、Chrome、其他 App、跨會話委派或所有截圖情境正常。截圖品質未驗收。
- 自動檢查是 App 執行期間每 60 秒觀察本機資料，不是關閉 App 後仍運作的服務。自動修復預設關閉；需要使用者在 App 中確認來源範圍後啟用，有防重與停點保護。

## 開發者

在來源根目錄執行：

```sh
/usr/bin/python3 -m unittest discover -s tests -p 'test_*.py'
/usr/bin/python3 tests/run_model_tests.py
bash build.sh
```

需要 Xcode Command Line Tools。建置產物位於 `dist/Computer Use Doctor V9 Preview.app`。測試使用隔離資料；原生模型測試不是實際 GUI 成功證據。公開版使用獨立 Bundle ID，與私人 V9 的 App／偏好分開，但讀取的是執行者自己的 Codex 環境，故不要讓兩版同時修復同一快取。

測試完成後可執行 `bash package.sh`，產生 App ZIP、乾淨來源壓縮包與 SHA256SUMS。打包只納入列出的來源／通用文件，不打包家目錄、官方 App、登入配置或歷史報告。

## 授權與來源

保留原修復工具的 MIT 授權及 Souitou-iop 著作權聲明，見 [LICENSE](LICENSE)。新增公開版路徑適配、App 與驗證邏輯隨本專案 MIT 條款提供；來源與依賴见 [第三方聲明](docs/THIRD-PARTY-NOTICES.md)。不附帶 OpenAI 專有 App／工具二進位、登入資料或任何人的私人設定。
