# dj fat 新歌追蹤 MCP

Python 3.9+ 本機 stdio MCP，無需額外套件。實作 MCP 2025-03-26 的初始化與工具介面；客戶端需接受此協定版本。不提供遠端 HTTP 端點。

追蹤設定預設使用專案的 `release-watch.json`：Said the Sky、台灣時間每天 08:00。儲存庫中的收件地址留空；個人設定請保存至 `.local/watch-config.json`，服務會優先讀取該檔，不將收件地址上傳。

首次設定時，將根目錄的 `release-watch.json` 複製至 `.local/watch-config.json`，在本機填入 `recipient_email`，並將檔案權限設為 600。下文提到的藝人 ID 與排程狀態也使用這份本機設定。

## MCP 工具

| 工具 | 行為 |
| --- | --- |
| `get_watch_status` | 查看設定與憑證是否就緒，不回傳秘密 |
| `check_new_releases` | 查詢 Spotify 新作品，不寄信 |
| `preview_notification` | 查詢並預覽郵件，不寄信 |
| `send_release_notification` | 寄送尚未通知的新作品；無新作品不寄信 |

查詢可指定 `since`、`through`，格式為 `YYYY-MM-DD`。預設查詢昨天至今天，以涵蓋早上檢查後才發行的作品。排程通知會從上次成功查詢日期接續；第一次採用昨天至今天。作品按 Spotify 發行項目通知，包含單曲、專輯與合作作品，並非逐首展開專輯曲目。缺少精確日期的作品不推測日期。

## 連接 MCP

將 `mcp-config.json` 中的伺服器設定合併至支援 `mcpServers` 的客戶端設定，保留其既有伺服器。其他客戶端請使用相同的 command 與 args。路徑為目前電腦的絕對路徑，搬移專案時須修改。

可先執行以下指令檢查狀態：

```bash
python3 release-watch-mcp/server.py --status
```

## Spotify 憑證

在 [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) 建立應用，取得 Client ID 與 Client Secret。

```bash
mkdir -p release-watch-mcp/.local
cp release-watch-mcp/secrets.example.json release-watch-mcp/.local/secrets.json
chmod 700 release-watch-mcp/.local
chmod 600 release-watch-mcp/.local/secrets.json
```

在本機填入這兩個值，不貼到聊天中。若搜尋無法唯一確認藝人，可在 `release-watch.json` 加上 `spotify_artist_id`；服務會核對其藝人名稱。

Spotify 的開發模式限制或帳號權限可能影響 API 存取；收到 401、403、429 時會回報錯誤，不將失敗查詢當成沒有新歌。

## Gmail 授權

此 MCP 使用自己的 Gmail API 授權，與 ChatGPT Gmail 插件分開。插件的登入不能直接作為本機服務的憑證。

1. 依 [Google Gmail Python quickstart](https://developers.google.com/workspace/gmail/api/quickstart/python) 建立 Google Cloud 專案、啟用 Gmail API、設定 OAuth 同意畫面與測試使用者。
2. 建立 **Desktop app** OAuth 用戶端，下載 JSON，保存為 `release-watch-mcp/.local/google-client.json`，設為僅本人可讀。
3. 執行以下指令，在瀏覽器登入寄件帳號並同意 `gmail.send` 授權：

```bash
python3 release-watch-mcp/authorize_gmail.py
```

授權程式只監聽本機回呼，使用 state 與 PKCE，最多等待五分鐘。refresh token 保存在 `.local/gmail-token.json`，檔案權限為 600。`.local` 已排除版本控制。Google 測試模式可能導致授權過期；過期後需重新授權。

## 每日排程

MCP 連線本身不會定時執行。macOS LaunchAgent 負責每日早上 08:00 呼叫同一服務。

先產生排程檔，不啟用：

```bash
python3 release-watch-mcp/install_schedule.py
```

完成 Spotify 憑證與 Gmail 授權，確認 macOS 時區為 Asia/Taipei 後，啟用：

```bash
python3 release-watch-mcp/install_schedule.py --enable
```

成功載入並驗證排程後，才會將 `release-watch.json` 的 `schedule_created` 改為 `true`。電腦須開機並登入；睡眠可能延後執行，關機期間無法保證準時通知。若需要電腦關機仍能每日準時執行，需另部署至常駐主機。

停用排程：

```bash
launchctl bootout "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.djfat.release-watch.plist"
```

停用後請將 `release-watch.json` 的 `schedule_created` 改為 `false`、`status` 改為 `pending_setup`。

## 寄送與錯誤處理

寄送至設定的收件人，使用完成 OAuth 的 Gmail 帳號。確認寄送成功後記錄作品 ID，避免再次通知。跨 MCP 與排程程序的寄送以檔案鎖序列化。

若寄信後連線中斷，無法確認 Gmail 是否已收件，會保留 `.local/state.json` 的 `pending_send` 並停止後續寄送。先查看 Gmail 寄件備份：已寄出則將該批 ID 加入對應收件人的 `deliveries`；確認未寄出則可重試。處理後移除 `pending_send`。不自動重寄結果不明的郵件。

## 驗證

```bash
python3 -m unittest discover -s release-watch-mcp -p 'test_*.py' -v
```

測試使用模擬 API，不讀取真實憑證、不寄信。真正的 Spotify 查詢與 Gmail 寄信須在授權完成後驗證。

參考：[MCP stdio 規格](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports)、[Spotify Artist Albums](https://developer.spotify.com/documentation/web-api/reference/get-an-artists-albums)、[Gmail 寄信 API](https://developers.google.com/workspace/gmail/api/guides/sending)。
