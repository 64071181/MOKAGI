
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
    "updata":"202604301052"
}

import logging, os
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
        help_text = (
            "📖 長期記憶\n使用下方按鈕快速操作，或直接輸入命令："
            "📖 長期記憶使用說明：\n\n"
            "/memory remember <內容>\n  例：/memory remember 我喜歡喝咖啡\n\n"
            "/memory recall <關鍵詞>\n  例：/memory recall 喜歡喝什麼\n\n"
            "/memory list\n 列出所有記憶\n\n"
            "/memory forgetall\n 忘記所有記憶\n\n"
            )
        return (help_text)

    parts = args.split(maxsplit=1)
    subcmd = parts[0].lower()
    content = parts[1] if len(parts) > 1 else ""

    try:
        col = _col()

        if subcmd == "remember":
            if not content:
                return "用法: /memory remember <內容>\n  例：/memory remember 我喜歡喝咖啡\n\n"
            col.add(
                documents=[content],
                metadatas=[{"chat_id": chat_id}],
                ids=[f"{chat_id}_{col.count()}"]
            )
            return "✅ 已記住。"

        elif subcmd == "recall":
            if not content:
                return "用法: /memory recall <關鍵詞>\n  例：/memory recall 喜歡喝什麼"
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
