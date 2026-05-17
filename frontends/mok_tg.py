"""
mok_tg.py
Telegram 適配器 - 支持流式輸出（實時顯示思考過程）
核心對話能力由 mokagi 提供。
202605171733
"""

import asyncio
import logging
import os
import re
import sys
import json
from functools import partial

from telegram import Update, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# 導入統一核心模塊
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import mokagi
from mokagi import process_message, clear_history, reload_tools, execute_multi_step, MOKAGI_home

# ================== 載入配置文件（僅用於 Telegram 特有配置）==================
def load_agent_config():
    MOK_AGENT_NAME = os.environ.get("MOK_AGENT_NAME")
    if not MOK_AGENT_NAME:
        proc_name = os.environ.get("PM2_PROGRAM_NAME") or sys.argv[0]
        # 匹配進程名中的 agent 名稱，例如 mok_溟
        match = re.search(rf'{MOKAGI_home}_(.+)$', proc_name)
        MOK_AGENT_NAME = match.group(1) if match else "default"
    # 配置文件路徑：~/.mok/.{agent_name}
    config_path = os.path.join(os.path.expanduser("~"), f".{MOKAGI_home}", f".{MOK_AGENT_NAME}")
    if not os.path.exists(config_path):
        raise RuntimeError(f"配置文件 {config_path} 不存在")
    config = {}
    with open(config_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, value = line.split('=', 1)
                config[key.strip()] = value.strip()
    return config, MOK_AGENT_NAME

config, MOK_AGENT_NAME = load_agent_config()

# Telegram 特有配置
MOK_TG_TOKEN = config.get("MOK_TG_TOKEN")
if not MOK_TG_TOKEN:
    raise RuntimeError("配置文件中缺少 MOK_TG_TOKEN")
ADMIN_CHAT_ID = config.get("ADMIN_CHAT_ID", "")
ALLOWED_USERS_STR = config.get("MOK_ALLOWED_USERS", "")
ALLOWED_USERS = set()
if ALLOWED_USERS_STR:
    for uid in ALLOWED_USERS_STR.split(","):
        uid = uid.strip()
        if uid:
            ALLOWED_USERS.add(int(uid) if uid.isdigit() else uid)

# 固定消息文本
WELCOME_MSG = config.get("MOK_welcome_msg", "你好！我是有記憶的 AI 助手。")
START_MSG = config.get("MOK_start_msg", "🎉 已成功部署並24小時在線！")
UNAUTHORIZED_MSG = config.get("MOK_unAllowed_msg", "您未獲得使用權限。")

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)

# ================== 輔助函數 ==================
def sanitize(s: str) -> str:
    """清理字符串中的不可見字符"""
    s = re.sub(r'[\u200b\u200c\u200d\u200e\u200f\ufeff]', '', s)
    s = ''.join(ch for ch in s if ch.isprintable() or ch in ('\n', '\t'))
    return s.strip()

# ================== 流式回調函數（核心） ==================
async def stream_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, temp_msg, event: dict):
    """
    處理 mokagi 產生的事件，實時更新 Telegram 消息
    event 格式：
        {"type": "think", "content": "思考內容片段"}
        {"type": "reply", "content": "回覆內容片段"}
        {"type": "done"}
    """
    try:
        # 為思考內容建立累積器
        if not hasattr(stream_callback, "think_content"):
            stream_callback.think_content = ""
        if not hasattr(stream_callback, "full_reply"):
            stream_callback.full_reply = ""

        if event["type"] == "think":
            stream_callback.think_content += event["content"]
            # 只顯示思考部分（回覆還沒開始）
            new_text = f"💭\n{stream_callback.think_content}"
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=temp_msg.message_id,
                text=new_text,
                parse_mode="Markdown"
            )
        elif event["type"] == "reply":
            stream_callback.full_reply += event["content"]
            # 同時顯示思考內容和回覆內容
            new_text = f"```🤔\n{stream_callback.think_content}🤔```\n\n💬 回覆：\n{stream_callback.full_reply}"
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=temp_msg.message_id,
                text=new_text,
                parse_mode="Markdown"
            )
        elif event["type"] == "done":
            final_reply = stream_callback.full_reply or "（無回覆）"
            # 最終也保留思考內容
            new_text = f"```💡\n{stream_callback.think_content}💡```\n\n💬 回覆：\n{final_reply}"
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=temp_msg.message_id,
                text=new_text,
                parse_mode="Markdown"
            )
            # 清理累積器，為下一次對話準備
            del stream_callback.think_content
            del stream_callback.full_reply
    except Exception as e:
        logging.error(f"流式回調出錯: {e}")


# ================== Telegram 命令處理器 ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(WELCOME_MSG)

async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    clear_history(chat_id)
    await update.message.reply_text("記憶已清除，我們重新開始。")

async def tools_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from mokagi import tool_handler
    tools = tool_handler.get_tools()
    text = "🧰 **已安裝的工具:**\n"
    for mod in tools.values():
        if hasattr(mod, "PLUGIN_INFO"):
            info = mod.PLUGIN_INFO
            text += f"  {info['command']} — {info['description']}\n"
    text += "\n ➕ [增加工具](https://github.com/64071181/MokAgi/tree/main/tools)"
    await update.message.reply_text(text, parse_mode="Markdown", disable_web_page_preview=True)

async def reload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reload_tools()
    await update_bot_commands(context.application)
    await update.message.reply_text("✅ 工具已重新加載。")

async def update_bot_commands(app):
    from mokagi import tool_handler
    base_commands = [
        BotCommand(sanitize("start"), sanitize("開始對話")),
        BotCommand(sanitize("clear"), sanitize("清除會話記憶")),
        BotCommand(sanitize("tools"), sanitize("工具箱")),
        BotCommand(sanitize("reload"), sanitize("重新加載工具")),
    ]
    plugin_commands = []
    for mod in tool_handler.get_tools().values():
        if hasattr(mod, "PLUGIN_INFO"):
            info = mod.PLUGIN_INFO
            cmd = sanitize(info["command"]).lstrip("/")
            desc = sanitize(info["description"])
            if cmd and desc:
                plugin_commands.append(BotCommand(cmd, desc))
    await app.bot.set_my_commands(base_commands + plugin_commands)

async def send_welcome(app):
    if ADMIN_CHAT_ID:
        try:
            await app.bot.send_message(chat_id=ADMIN_CHAT_ID, text=START_MSG)
        except Exception as e:
            logging.warning(f"無法發送歡迎消息給 {ADMIN_CHAT_ID}: {e}")

# ================== 消息處理（流式） ==================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    chat_id = str(update.message.chat_id)

    # 權限檢查
    if ALLOWED_USERS and str(chat_id) not in map(str, ALLOWED_USERS):
        await update.message.reply_text(UNAUTHORIZED_MSG)
        return

    # ---------- 直接處理以 '/' 開頭的命令 ----------
    if user_text.startswith('/'):
        print(f"收到 / 命令: {user_text}")
        # 導入 tool_handler（已在 mokagi 中導入，這裡直接引用）
        from mokagi import tool_handler
        # 調用統一的命令處理函數（非流式）
        result = await tool_handler.process_message(
            user_text=user_text,
            chat_id=chat_id,
            ollama_api=mokagi.OLLAMA_API,
            model_name=mokagi.MOK_MODEL_NAME,
            cmd_map=tool_handler.get_cmd_map(),
            tools=tool_handler.get_tools()
        )
        if result:
            # 如果命令被處理，直接發送結果並返回
            await update.message.reply_text(result, parse_mode='HTML')
            return
        # 如果沒有匹配的命令，繼續下面的流程（可能當作普通聊天處理）
        # 注意：這裡不返回，讓後續流程嘗試意圖識別或普通聊天

    # 特殊處理：工作流自動執行標記（由 workflow 工具返回）
    if user_text.startswith("WORKFLOW_AUTO_EXEC:"):
        print(f"收到 工作流: {user_text}")
        parts = user_text.split(":", 3)
        if len(parts) >= 4:
            goal = parts[3].split(":", 1)[0] if ":" in parts[3] else parts[3]
            steps_json = parts[3].split(":", 1)[1] if ":" in parts[3] else ""
            if steps_json:
                steps = json.loads(steps_json)
                result = await execute_multi_step(chat_id, goal, forced_steps=steps)
                await update.message.reply_text(result)
                return
        await update.message.reply_text("❌ 工作流自動執行標記無效")
        return

    # 普通消息：發送臨時消息，然後通過流式回調更新
    temp_msg = await update.message.reply_text("💭 思考中...")
    try:
        cb = partial(stream_callback, update, context, temp_msg)
        await process_message(user_id=chat_id, text=user_text, stream_callback=cb)
    except Exception as e:
        logging.exception("處理消息時出錯")
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=temp_msg.message_id,
            text=f"❌ 處理消息時出錯: {str(e)}"
        )

# ================== 主函數 ==================
def main():
    reload_tools()
    app = ApplicationBuilder().token(MOK_TG_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(CommandHandler("tools", tools_command))
    app.add_handler(CommandHandler("reload", reload))
    app.add_handler(MessageHandler(filters.TEXT, handle_message))

    loop = asyncio.get_event_loop()
    loop.run_until_complete(update_bot_commands(app))
    loop.run_until_complete(send_welcome(app))

    print(f"✅ {MOK_AGENT_NAME} 啟動中... （流式輸出已啟用）")
    app.run_polling()

if __name__ == "__main__":
    main()