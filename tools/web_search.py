PLUGIN_INFO = {
    "command": "/search",          # Telegram 命令
    "icon": "🔍",
    "handler": "handle_web_search",
    "description": "搜索網頁（由 DuckDuckGo 提供）",
    "intent_keywords": [
        ("上網找", "/search")
    ],
    "updata": "202605041152"
}

import logging
import html

# 嘗試導入搜索庫，記錄是否成功
DDGS_AVAILABLE = False
try:
    from duckduckgo_search import DDGS
    DDGS_AVAILABLE = True
except ImportError:
    DDGS_AVAILABLE = False
    logging.warning("duckduckgo-search 庫未安裝，搜索功能不可用")

def handle_web_search(args: str, chat_id: str = None) -> str:
    """
    同步搜索函數，使用穩定可靠的 duckduckgo-search 庫
    """
    # 檢查庫是否可用
    if not DDGS_AVAILABLE:
        msg = """❌ 搜索功能不可用：`duckduckgo-search`

請使用以下命令安裝（需要管理員權限）：

<pre> /admin pip install duckduckgo-search </pre>

發送後會要求二次確認，輸入確認碼即可自動安裝。
        """

        return msg


    query = args.strip()
    if not query:
        return "🔎 用法：`/search 關鍵詞`\n例如：`/search 今日新聞`"

    logging.info(f"Web search (DDGS): {query}")

    try:
        # 使用 DDGS 庫執行搜索，獲取最多5個結果
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
    except Exception as e:
        logging.exception("網頁搜索請求失敗")
        return f"❌ 搜索失敗: {html.escape(str(e))}"

    if not results:
        return f"🔍 未找到與「{html.escape(query)}」相關的結果。"

    reply = f"🔍 **搜索「{html.escape(query)}」結果：**\n\n"
    for idx, res in enumerate(results, 1):
        title = html.escape(res.get('title', ''))
        body = html.escape(res.get('body', ''))
        href = res.get('href', '')

        reply += f"{idx}. **{title}**\n"
        if body:
            reply += f"   {body[:200]}...\n"  # 截取摘要前200字
        reply += f"   🔗 {href}\n\n"
        if len(reply) > 3800:
            reply += "\n...(結果過多，已截斷)"
            break

    return reply