# make-music · dj fat

音樂製作文章收藏、瀏覽與 Spotify 新作品追蹤工具。

## 專案內容

- [agents/agent.md](agents/agent.md)：dj fat 的定位與工作方式。
- [skills/article-to-json/SKILL.md](skills/article-to-json/SKILL.md)：依文章 URL 與標籤截圖整理 JSON 的技能。
- [articles.json](articles.json)：文章收藏資料，不包含摘要。
- `article-browser/`：支援搜尋、標籤篩選與排序的文章瀏覽網頁。
- [release-watch-mcp/README.md](release-watch-mcp/README.md)：本機 Spotify／Gmail MCP、授權與每日排程說明。
- [release-watch.json](release-watch.json)：新作品追蹤設定。

## 瀏覽文章

需求：Python 3.9 或更新版本，無需安裝額外套件。

在專案根目錄執行：

```bash
python3 article-browser/serve.py
```

開啟 http://127.0.0.1:8000。網頁會讀取專案中的最新 `articles.json`。也可直接開啟 `article-browser/dist/index.html` 並匯入 JSON。

## 新作品追蹤 MCP

```bash
python3 release-watch-mcp/server.py --status
```

完整設定請參閱 [MCP 說明](release-watch-mcp/README.md)。接入設定中的絕對路徑須改成你本機的專案位置。Spotify 憑證、Gmail OAuth 授權與排程必須另外完成；下載或連接 MCP 不會自動啟用寄信。

本機秘密與狀態保存在 `release-watch-mcp/.local/`，不納入版本控制。

## 測試

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s release-watch-mcp -p 'test_*.py' -v
```

測試使用模擬 API，不寄送真實郵件。真實 Spotify／Gmail 操作需先完成憑證設定與授權。
