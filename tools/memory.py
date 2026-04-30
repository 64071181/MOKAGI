
PLUGIN_INFO = {
    "command": "/memory",
    "icon":"🧠",
    "description": "長期記憶 (remember, recall, list, forgetall)",
    "handler": "handle_memory",
    "intent_keywords": [
        ("記住", "/memory remember"),
        ("記得", "/memory remember"),
        ("儲存", "/memory remember"),
        ("保存", "/memory remember"),

        ("之前", "/memory recall"),
        ("我說過", "/memory recall"),
        ("找出", "/memory recall"),

        ("列出記憶", "/memory list"),
        ("所有記憶", "/memory list"),
        ("顯示記憶", "/memory list"),

        ("忘記所有", "/memory forgetall"),
        ("清空記憶", "/memory forgetall"),
        ("刪除所有記憶", "/memory forgetall")
    ],
    "updata":"202605010257"
}

import logging, os, re
import chromadb
from chromadb.config import Settings
from telegram import ReplyKeyboardMarkup, KeyboardButton

# 明确指定数据存储路径
CHROMA_PATH = os.path.join(os.path.expanduser("~"), ".MokAgi", "chroma_data")

try:
    _client = chromadb.PersistentClient(path=CHROMA_PATH, settings=Settings(anonymized_telemetry=False))
    _collection = _client.get_or_create_collection(name="mokagi_memory")
    MISSING_DEPS = False
except ImportError:
    MISSING_DEPS = True
    _collection = None

def _col():
    global _client, _collection
    if _client is None:
        _client = chromadb.PersistentClient(path=CHROMA_PATH, settings=Settings(anonymized_telemetry=False))
        _collection = _client.get_or_create_collection(name="mokagi_memory")
    return _collection

async def recall_memory(chat_id: int, query: str, n_results: int = 1) -> str:
    if MISSING_DEPS:
        return ""
    try:
        col = _col()
        results = col.query(
            query_texts=[query],
            n_results=n_results,
            where={"chat_id": str(chat_id)}
        )
        docs = results.get("documents", [[]])[0]
        if docs:
            return "\n".join(docs)
    except Exception as e:
        logging.error(f"記憶檢索錯誤: {e}")
    return ""

def handle_memory(args: str, chat_id: str = None):
    if MISSING_DEPS:
        return "❌ 記憶工具缺少依賴，請在終端執行：\npip install chromadb"
    if chat_id is None:
        return "❌ 無法識別使用者。"

    args = args.strip()
    if not args:
        help_text = '''
🧠 長期記憶使用說明：
    (使用下方按鈕快速操作，或直接輸入命令)
    <pre>/memory remember 內容</pre>
    例：/memory remember 我喜歡喝咖啡
    <pre>/memory recall 關鍵詞</pre>
    例：/memory recall 喜歡喝什麼

    列出所有記憶<pre>/memory list</pre>

    忘記所有記憶<pre>/memory forgetall</pre>

=====
🧩 自然語言意圖辨識：
            '''
        # 动态添加 intent_keywords（不转义）
        for keyword, cmd in PLUGIN_INFO["intent_keywords"]:
            help_text += f'   "{keyword}" → {cmd}\n'
        return help_text

    parts = args.split(maxsplit=1)
    subcmd = parts[0].lower()
    content = parts[1] if len(parts) > 1 else ""

    try:
        col = _col()

        # 处理 remember 子命令
        if subcmd == "remember":
            if not content:
                return "用法: /memory remember 內容\n  例：/memory remember 我喜歡喝咖啡\n\n"
            # ----- 新增：人稱標準化（將用戶對自己的描述轉為無歧義的第三人稱）-----
            normalized = content
            # 移除開頭的「記得」或「記住」
            normalized = re.sub(r'^(?:記得|記住)\s*', '', normalized)
            # 將「我是」→「用戶的」
            normalized = re.sub(r'我是', '用戶是', normalized)
            # 將「我叫」→「用戶名字是」
            normalized = re.sub(r'我叫', '用戶叫', normalized)
            # 將「我」單獨（非「我的」）→「用戶」
            normalized = re.sub(r'\b我\b', '用戶', normalized)
            # 將「你/妳」→「助手」（如果用戶提到了助手）
            normalized = re.sub(r'你|妳', '我', normalized)
            # 可選：將「我的」→「用戶的」
            normalized = re.sub(r'我的', '用戶的', normalized)
            # ------------------------------------------------------------------
            col.add(
                documents=[normalized],
                metadatas=[{"chat_id": chat_id}],
                ids=[f"{chat_id}_{col.count()}"]
            )
            return f"✅ 已記住（標準化為：{normalized}）"

        elif subcmd == "recall":
            if not content:
                return "用法: /memory recall 關鍵詞\n  例：/memory recall 喜歡喝什麼"
            results = col.query(
                query_texts=[content],
                n_results=3,
                where={"chat_id": chat_id}
            )
            docs = results.get("documents", [[]])[0]
            if not docs:
                return "沒有找到相關記憶。"
            reply = "🧠 回憶：\n"
            for d in docs:
                reply += f"· {d}\n"
            return reply

        elif subcmd == "list":
            results = col.get(
                where={"chat_id": chat_id},
                limit=10
            )
            docs = results.get("documents", [])
            if not docs:
                return "目前沒有任何記憶。"
            reply = "📋 最近記憶：\n"
            for i, d in enumerate(docs):
                reply += f"{i+1}. {d}\n"
            return reply

        elif subcmd == "forgetall":
            col.delete(where={"chat_id": chat_id})
            return "🗑 記憶已清空。"

        else:
            return f"未知子命令: {subcmd}"

    except Exception as e:
        logging.error(f"記憶工具錯誤: {e}")
        return f"❌ 記憶操作失敗: {e}"