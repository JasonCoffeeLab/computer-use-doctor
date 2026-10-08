# 公開版驗證與發布停點

核對日期：2026-10-08（台北）。本預覽使用獨立 Bundle ID：org.computer-use-doctor.preview.v9。

## 本次已執行

- 91 項 Python 隔離測試通過，包括快取／交易／恢復既有保護，以及新增的不同使用者路徑、空白路徑、未知命令、越界連結、缺少 CLI、錯誤 App 身份及自身路徑核對。
- 原生模型 smoke 通過：實測入口、面板計算、無活動批次保護、來源副本與本機副本匹配、防止覆蓋修改後目標。這是隔離模型測試，不是滑鼠操作實測。
- Apple Silicon／macOS 14 目標 App 已編譯，臨時簽署與嚴格簽署檢查通過。臨時簽署不是 Developer ID／公證。
- 本機公開版「開始檢查」真實 GUI 驗收通過：新批次、5 次實際點擊、算式 `1 + 1`、結果 `2`。在非個人固定路徑的暫存 App 執行；這不是另一台乾淨 Mac 的驗收。
- 本機「修復並核查全部項目」在零可修復候選情況下再次啟動新批次並通過相同五次操作核對；没有將舊結果當成新驗收，沒有修改快取。
- 公開來源限定 Sources、Resources、tests、build.sh、LICENSE 及新增通用文件，沒有納入私人 V9 的歷史文件／操作回執／工作資料。
- App ZIP 在獨立本機暫存目錄解壓後通過嚴格簽署檢查。iCloud 展開副本因 Finder／資源附加資料未通過同一檢查；交付採用 ZIP，不將 iCloud 展開副本當成已驗證可用 App。

## 未執行或未完成

- 另一個 macOS 帳號、乾淨 Mac、首次缺依賴、一般使用者下載後首次啟動的整體驗收。
- 公開版的實際登出／登入、重開機自啟動驗收。
- Intel Mac、Windows、npm／Homebrew CLI、其他官方桌面工具契約相容性。
- 截圖品質驗收；已知私人環境曾出現很小的縮圖，不能保證截圖功能已修復。
- Developer ID 簽署、公證與 Gatekeeper 對一般下載者的驗收。
- 發布目的地與帳號已核對為 JasonCoffeeLab/computer-use-doctor。上傳、Release 及遠端檔案讀回以 GitHub 實際結果核對，不能以本機檔案存在代替。

以上未驗項不得寫成通過。此版僅為公開預覽，不能標成普遍適用的穩定版。

## 發布方式

原始碼倉庫收納通用文件、source、tests 及 LICENSE；二進位 App ZIP 與 SHA-256 附在 GitHub Releases，標明 Pre-release。不要提交 dist、.build-cache、auth.json、config.toml 或私人診斷。

普通使用者的正式可下載版應先完成簽署／公證與乾淨環境驗收。若先公開來源或本機簽署預覽，發布頁必須保留相應限制，不附關閉安全保護的指令。
