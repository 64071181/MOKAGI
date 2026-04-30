PLUGIN_INFO = {
    "command": "/intent",
    "icon":"🧩",
    "description": "自然語言意圖辨識 (自動轉換指令，支援動態新增外掛)",
    "handler": "dummy_handler",
    "update": "202605010257"
}


import httpx
import json
import logging
import re
from typing import Dict, Any


# 全域變數，由主程式透過鉤子傳入
_cmd_map = {}
_tools = {}


def build_keyword_map(cmd_map: dict, tools: dict) -> Dict[str, str]:
    """返回 {關鍵詞: 完整命令} 映射，支援兩種格式：
       - 簡單關鍵詞列表: ["關鍵詞"] → 映射到該插件的默認命令（cmd）
       - 元組列表: [("關鍵詞", "/完整 命令")] → 映射到指定的完整命令
    """
    kw_map = {}
    for cmd, handler in cmd_map.items():
        # 找到對應的 module
        mod = None
        for name, m in tools.items():
            if hasattr(m, "PLUGIN_INFO") and m.PLUGIN_INFO.get("command") == cmd:
                mod = m
                break
        if not mod or not hasattr(mod, "PLUGIN_INFO"):
            continue
        info = mod.PLUGIN_INFO
        keywords_raw = info.get("intent_keywords", [])
        if not keywords_raw:
            # 若無關鍵詞，可根據指令名稱和描述產生簡單詞（原有邏輯）
            desc = info.get("description", "")
            words = re.findall(r'[\u4e00-\u9fa5]+', desc)
            keywords = words if words else [cmd.lstrip("/")]
            for kw in keywords:
                kw_map[kw.lower()] = cmd
        else:
            # 處理新的元組格式或傳統列表
            for item in keywords_raw:
                if isinstance(item, tuple) and len(item) == 2:
                    keyword, full_cmd = item
                    kw_map[keyword.lower()] = full_cmd
                elif isinstance(item, str):
                    # 傳統格式：關鍵詞映射到插件的根命令
                    kw_map[item.lower()] = cmd
                else:
                    logging.warning(f"忽略錯誤格式的 intent_keywords 項目: {item}")
    return kw_map


async def rule_based_intent(user_text: str, kw_map: dict) -> tuple:
    """回傳 (完整命令, 參數) 或 (None, None)"""
    text_lower = user_text.lower()
    for kw, full_cmd in kw_map.items():
        if kw in text_lower:
            # 提取參數：移除第一個匹配的關鍵詞後的部分
            # 注意：用戶訊息可能包含關鍵詞的前後文，直接移除關鍵詞
            # 簡單做法：用正則替換第一個出現的關鍵詞（不區分大小寫）
            import re
            pattern = re.compile(re.escape(kw), re.IGNORECASE)
            args = pattern.sub('', user_text, count=1).strip()
            return full_cmd, args
    return None, None




async def llm_intent(user_text: str, cmd_map: dict, tools: dict, ollama_api: str, model_name: str) -> tuple:
    """使用 LLM 分類意圖，動態生成 prompt（通用版，不硬編碼任何工具）"""
    # 建立指令描述列表
    cmd_desc = []
    for cmd, handler in cmd_map.items():
        if cmd in ["/start", "/clear", "/tools", "/reload"]:
            continue
        mod = None
        for name, m in tools.items():
            if hasattr(m, "PLUGIN_INFO") and m.PLUGIN_INFO.get("command") == cmd:
                mod = m
                break
        desc = cmd
        if mod and hasattr(mod, "PLUGIN_INFO"):
            desc = mod.PLUGIN_INFO.get("description", cmd)
        cmd_desc.append(f"- {cmd}: {desc}")

    prompt = f"""你是一個意圖分類助手。根據使用者輸入，輸出 JSON: {{"command": "指令名稱", "args": "提取的參數"}}
如果沒有任何指令符合，輸出 {{"command": "none"}}。

可用的指令與說明：
{chr(10).join(cmd_desc)}

重要指引：
- 若指令支援子命令（如 /memory 有 remember/recall/list/forgetall），請在 args 中以子命令開頭，例如 "remember 我喜歡咖啡" 或 "list"。
- 若指令不需要參數，args 留空字串。

使用者輸入：{user_text}
只輸出 JSON，不要有其他文字。"""

    payload = {
        "model": model_name,
        "prompt": prompt,
        "stream": False,
        "options": {"num_predict": 120, "temperature": 0.1}
    }
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(ollama_api, json=payload)
            resp.raise_for_status()
            data = resp.json()
            output = data.get("response", "").strip()
            if "{" in output and "}" in output:
                output = output[output.find("{"):output.rfind("}")+1]
            result = json.loads(output)
            cmd = result.get("command", "none")
            args = result.get("args", "")
            if cmd != "none" and cmd in cmd_map:
                return cmd, args
    except Exception as e:
        logging.warning(f"LLM意圖辨識失敗: {e}")
    return None, None




async def handle_intent(update, context, user_text: str, chat_id: int,cmd_map: dict, tools: dict,ollama_api: str, model_name: str) -> bool:
    """主鉤子函數，需要主程式傳入 tools 物件（需修改主程式呼叫）"""
    global _cmd_map, _tools
    _cmd_map = cmd_map
    _tools = tools

    # 將接收到的模型設定儲存或直接傳遞給內部函式
    # 可以設為模組變數供其他函式使用
    global _ollama_api, _model_name
    _ollama_api = ollama_api
    _model_name = model_name

    # 1. 規則比對
    kw_map = build_keyword_map(cmd_map, tools)
    cmd, args = await rule_based_intent(user_text, kw_map)
    if not cmd:
        # 2. LLM 後備
        cmd, args = await llm_intent(user_text, cmd_map, tools, ollama_api, model_name)

    if not cmd:
        return False

    # ========== 修改開始：處理完整命令（如 "/memory remember"）==========
    handler = None
    final_args = args

    # 如果 cmd 包含空格，表示是完整命令（例如 "/memory remember"）
    if " " in cmd.lstrip("/"):   # 避免根命令本身有空格
        parts = cmd.split(maxsplit=1)
        root_cmd = parts[0]      # 例如 "/memory"
        sub_cmd_part = parts[1]  # 例如 "remember"
        # 將子命令與原本的 args 合併（注意：rule_based 的 args 已經是去掉關鍵詞後的剩餘部分）
        if args:
            final_args = f"{sub_cmd_part} {args}"
        else:
            final_args = sub_cmd_part
        handler = cmd_map.get(root_cmd)
    else:
        # 一般情況，cmd 本身就是根命令（如 "/memory"），args 可能已含子命令（如 "remember 咖啡"）

        # 執行對應指令
        handler = cmd_map.get(cmd)
        final_args = args   # 直接使用原始參數
    if handler:
        # 顯示臨時狀態（使用 root_cmd 或 cmd 作為顯示名稱）
        display_cmd = root_cmd if 'root_cmd' in locals() else cmd
        temp_msg = await update.message.reply_text(f"⏳ 正在執行 {display_cmd} ...")
        try:
            result = handler(final_args, str(chat_id))
            if isinstance(result, tuple):
                text, markup = result
                await context.bot.edit_message_text(
                    chat_id=temp_msg.chat_id,
                    message_id=temp_msg.message_id,
                    text=text,
                    reply_markup=markup
                )
            elif result is not None:
                await context.bot.edit_message_text(
                    chat_id=temp_msg.chat_id,
                    message_id=temp_msg.message_id,
                    text=result
                )
            else:
                await context.bot.edit_message_text(
                    "✅ 完成",
                    chat_id=temp_msg.chat_id,
                    message_id=temp_msg.message_id
                )
        except Exception as e:
            await context.bot.edit_message_text(
                f"❌ 執行意圖命令失敗: {e}",
                chat_id=temp_msg.chat_id,
                message_id=temp_msg.message_id
            )
        return True
    return False

def dummy_handler(args: str, chat_id: str = None):
    return "請使用自然語言觸發意圖辨識，例如「記得我喜歡喝咖啡」"