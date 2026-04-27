
PLUGIN_INFO = {
    "command": "/memory",
    "description": "長期記憶 (remember, recall, list, forgetall)",
    "handler": "handle_memory",
    "updata":"202604272035"
}

import logging
import chromadb
from chromadb.config import Settings

try:
    _client = chromadb.Client(Settings(anonymized_telemetry=False))
    _collection = _client.get_or_create_collection(name="mokagi_memory")
    MISSING_DEPS = False
except ImportError:
    MISSING_DEPS = True
    _collection = None

def _col():
    global _client, _collection
    if _client is None:
        _client = chromadb.Client(Settings(anonymized_telemetry=False))
        _collection = _client.get_or_create_collection(name="mokagi_memory")
    return _collection

def handle_memory(args: str, chat_id: str = None) -> str:
    if MISSING_DEPS:
        return "❌ 記憶插件缺少依賴，請在終端執行：\npip install chromadb"
    if chat_id is None:
        return "❌ 無法識別使用者。請在私聊中使用。"

    args = args.strip()
    if not args:
        return "📖 長期記憶使用說明：\n\n" \
               "/memory remember <內容>\n  例：/memory remember 我喜歡喝咖啡\n\n" \
               "/memory recall <關鍵詞>\n  例：/memory recall 喜歡喝什麼\n\n" \
               "/memory list\n\n" \
               "/memory forgetall"

    parts = args.split(maxsplit=1)
    subcmd = parts[0].lower()
    content = parts[1] if len(parts) > 1 else ""

    try:
        col = _col()

        if subcmd == "remember":
            if not content:
                return "用法: /memory remember <內容>"
            col.add(
                documents=[content],
                metadatas=[{"chat_id": chat_id}],
                ids=[f"{chat_id}_{col.count()}"]
            )
            return "✅ 已記住。"

        elif subcmd == "recall":
            if not content:
                return "用法: /memory recall <關鍵詞>"
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
        logging.error(f"記憶插件錯誤: {e}")
        return f"❌ 記憶操作失敗: {e}"
