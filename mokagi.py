"""
202605170422
mokagi.py - 統一 AI 對話核心模塊

設計目標：
- 一套代碼同時支持 Telegram、Web 等多種前端
- 保持所有現有 tools（web_search, memory, workflow, admin, intent...）不變
- 統一處理：直接命令 → 意圖識別 → 多步工作流 → 工具調用 → 自然化
- 提供流式輸出接口，前端只需傳入異步回調即可

使用示例（Telegram 適配器）：
    await mokagi.process_message(
        user_id=str(chat_id),
        text=user_message,
        stream_callback=partial(telegram_stream_callback, context, message)
    )

使用示例（Web SocketIO 適配器）：
    await mokagi.process_message(
        user_id=session_id,
        text=user_message,
        stream_callback=web_stream_callback
    )
"""

import asyncio
import hashlib
import html
import json
import logging
import os
import re
import sys
import time
from collections import defaultdict
from typing import Dict, List, Optional, Callable, Awaitable, Any, Tuple, Union, AsyncGenerator

import httpx

# 設置環境變量，放在所有導入之前
MOKAGI_home = "mok"
os.environ["MOKAGI_HOME"] = MOKAGI_home

# 導入工具管理模塊（獨立於前端）
import tool_handler

# 確保工具目錄在 Python 路徑中
TOOLS_DIR = os.path.expanduser(f"~/.{MOKAGI_home}/tools")
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

# ----------------------------------------------------------------------
# 配置加載（從環境變量或 agent 專屬配置文件）
# ----------------------------------------------------------------------

def load_agent_config(agent_name: str = None) -> Dict[str, str]:
    f"""
    加載當前 agent 的配置（通常位於 ~/.{MOKAGI_home}/.溟 或通過環境變量指定）
    如果未指定 agent_name，則嘗試從環境變量 MOK_AGENT_NAME 或 PM2 程序名推斷。
    返回配置字典，包含 MOK_MODEL_NAME, MOK_MODEL_api, 各項參數等。
    """
    config = {}
    if not agent_name:
        agent_name = os.environ.get("MOK_AGENT_NAME")
        if not agent_name:
            proc_name = os.environ.get("PM2_PROGRAM_NAME") or sys.argv[0]
            match = re.search(rf'{MOKAGI_home}_(.+)$', proc_name)
            agent_name = match.group(1) if match else "default"
    mokagi_name = MOKAGI_home  # 可改為環境變量
    config_path = os.path.join(os.path.expanduser("~"), f".{mokagi_name}", f".{agent_name}")
    if not os.path.exists(config_path):
        # 返回默認配置
        return {
            "MOK_MODEL_NAME": "qwen3:1.7b",
            "MOK_MODEL_api": "http://localhost:11434/api/generate",
            "MOK_num_ctx": "16384",
            "MOK_num_predict": "8192",
            "MOK_temperature": "0.8",
            "MOK_top_p": "0.9",
            "MOK_top_k": "50",
            "MOK_repeat_penalty": "1.5",
            "MOK_presence_penalty": "0.6",
            "MOK_frequency_penalty": "0.5",
            "MOK_MAX_HISTORY_ROUNDS": "6",
            "MOK_MEMORY_RECALL_COUNT": "3",
        }
    with open(config_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, val = line.split('=', 1)
                config[key.strip()] = val.strip()
    return config

# 全局配置（啟動時加載一次）
_agent_config = load_agent_config()
MOK_MODEL_NAME = _agent_config.get("MOK_MODEL_NAME", "qwen3:1.7b")
OLLAMA_API = _agent_config.get("MOK_MODEL_api", "http://localhost:11434/api/generate")
OLLAMA_OPTIONS = {
    "num_ctx": int(_agent_config.get("MOK_num_ctx", 16384)),
    "num_predict": int(_agent_config.get("MOK_num_predict", 8192)),
    "temperature": float(_agent_config.get("MOK_temperature", 0.8)),
    "top_p": float(_agent_config.get("MOK_top_p", 0.9)),
    "top_k": int(_agent_config.get("MOK_top_k", 50)),
    "repeat_penalty": float(_agent_config.get("MOK_repeat_penalty", 1.5)),
    "presence_penalty": float(_agent_config.get("MOK_presence_penalty", 0.6)),
    "frequency_penalty": float(_agent_config.get("MOK_frequency_penalty", 0.5)),
}
MAX_HISTORY_ROUNDS = int(_agent_config.get("MOK_MAX_HISTORY_ROUNDS", 6))
MEMORY_RECALL_COUNT = int(_agent_config.get("MOK_MEMORY_RECALL_COUNT", 3))

# ----------------------------------------------------------------------
# 對話歷史管理（內存存儲，可按需擴展為持久化）
# ----------------------------------------------------------------------
user_histories: Dict[str, List[Dict]] = defaultdict(list)  # {user_id: [{"user":..., "assistant":...}]}

def get_user_history(user_id: str) -> List[Dict]:
    return user_histories[user_id]

def add_to_history(user_id: str, user_msg: str, assistant_reply: str):
    hist = user_histories[user_id]
    hist.append({"user": user_msg, "assistant": assistant_reply})
    if len(hist) > MAX_HISTORY_ROUNDS:
        hist.pop(0)

def clear_history(user_id: str):
    user_histories[user_id] = []

# ----------------------------------------------------------------------
# LLM 調用封裝（支持流式與非流式，支持工具定義嵌入）
# ----------------------------------------------------------------------

async def call_llm(
    prompt: str,
    system_prompt: str = "",
    stream: bool = False,
    tools_def: Optional[List[dict]] = None,
    **override_options
) -> Union[str, AsyncGenerator[str, None]]:
    """
    統一的 Ollama 調用接口。
    - 如果 stream=True，返回異步生成器，yield 每個 token。
    - 如果 stream=False，返回完整字符串。
    - tools_def 會被嵌入到 prompt 中（簡單方式），不改變 API 格式。
    """
    options = OLLAMA_OPTIONS.copy()
    options.update(override_options)
    full_prompt = (system_prompt + "\n\n" + prompt) if system_prompt else prompt
    if tools_def:
        tools_desc = json.dumps(tools_def, ensure_ascii=False, indent=2)
        full_prompt = (
            "你是一個智能助手，可以調用以下工具來幫助用戶。\n"
            "如果需要調用工具，請只輸出一個 JSON 對象，格式如下：\n"
            '{"name": "工具名稱", "arguments": {...}}\n'
            "如果不需要調用工具，請直接以自然語言回答。\n\n"
            f"可用的工具：{tools_desc}\n\n" + full_prompt
        )

    payload = {
        "model": MOK_MODEL_NAME,
        "prompt": full_prompt,
        "stream": stream,
        "options": options
    }

    # 單次 LLM 調用確實需要超過 120 秒的超時。
    async with httpx.AsyncClient(timeout=120) as client:
        if stream:
            async def stream_gen():
                async with client.stream("POST", OLLAMA_API, json=payload) as resp:
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        try:
                            chunk = json.loads(line)
                            if 'response' in chunk:
                                yield chunk['response']
                            if chunk.get('done'):
                                break
                        except:
                            continue
            return stream_gen()
        else:
            resp = await client.post(OLLAMA_API, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data.get("response", "").strip()

# ----------------------------------------------------------------------
# 工具調用相關函數（複用 tool_handler，並擴展 Function Calling）
# ----------------------------------------------------------------------

def build_tool_definitions() -> List[dict]:
    """從所有已加載的工具中收集 tool_schema，用於 LLM 工具調用"""
    schemas = []
    tools_dict = tool_handler.get_tools()
    print(f"DEBUG: 工具数量 = {len(tools_dict)}")
    for name, mod in tools_dict.items():   # 注意这里使用 .items() 同时获取名称和模块
        print(f"DEBUG: 检查模块 {name}")
        if hasattr(mod, "PLUGIN_INFO"):
            print(f"  -> 有 PLUGIN_INFO, 键: {list(mod.PLUGIN_INFO.keys())}")
            if "tool_schema" in mod.PLUGIN_INFO:
                schemas.append(mod.PLUGIN_INFO["tool_schema"])
                print(f"  -> 已添加 tool_schema")
            else:
                print(f"  -> 警告: 缺少 tool_schema 键")
        else:
            print(f"  -> 警告: 没有 PLUGIN_INFO 属性")
    print(f"DEBUG: 最终收集到 {len(schemas)} 个 tool_schema")
    return schemas

def extract_tool_call(response_text: str) -> Optional[dict]:
    """從 LLM 回覆中提取 JSON 格式的工具調用"""
    try:
        start = response_text.find('{')
        end = response_text.rfind('}') + 1
        if start == -1 or end == 0:
            return None
        json_str = response_text[start:end]
        data = json.loads(json_str)
        if "name" in data and "arguments" in data:
            return data
    except:
        pass
    return None

def find_tool_handler(tool_name: str):
    """根據工具名稱（tool_schema.name）找到對應的 handler 函數"""
    for mod in tool_handler.get_tools().values():
        if hasattr(mod, "PLUGIN_INFO"):
            schema = mod.PLUGIN_INFO.get("tool_schema", {})
            if schema.get("name") == tool_name:
                handler_name = mod.PLUGIN_INFO.get("handler")
                if handler_name:
                    return getattr(mod, handler_name, None)
    return None

async def naturalize_tool_result(
    user_text: str,
    tool_name: str,
    raw_result: str,
    temp_msg_callback: Optional[Callable] = None
) -> str:
    """
    將工具返回的 JSON 結果通過自然化函數轉為口語句子。
    如果工具定義了 naturalize_func，則調用之；否則返回原始結果。
    """
    # 查找工具模塊
    target_mod = None
    for mod in tool_handler.get_tools().values():
        if hasattr(mod, "PLUGIN_INFO"):
            schema = mod.PLUGIN_INFO.get("tool_schema", {})
            if schema.get("name") == tool_name:
                target_mod = mod
                break
    if target_mod and hasattr(target_mod, "PLUGIN_INFO"):
        func_name = target_mod.PLUGIN_INFO.get("naturalize_func")
        if func_name:
            naturalize_func = getattr(target_mod, func_name, None)
            if naturalize_func:
                try:
                    # 兼容舊版簽名，但儘量傳遞 temp_msg_callback（適配器可選）
                    result = await naturalize_func(
                        user_text=user_text,
                        raw_result=raw_result,
                        ollama_api=OLLAMA_API,
                        model_name=MOK_MODEL_NAME,
                        temp_msg=None,  # 前端可自行實現流式更新
                        context=None
                    )
                    return result
                except Exception as e:
                    logging.warning(f"自然化函數調用失敗: {e}")
    # 備選：簡單的 JSON 轉文本
    try:
        data = json.loads(raw_result)
        if isinstance(data, dict) and "error" in data:
            return f"❌ 錯誤: {data['error']}"
        if isinstance(data, dict) and "results" in data:
            items = data["results"][:3]
            lines = [f"{i+1}. {item.get('title', '無標題')}\n   {item.get('body', '')[:100]}" for i, item in enumerate(items)]
            return "\n\n".join(lines)
    except:
        pass
    # 直接截斷返回
    if len(raw_result) > 1000:
        raw_result = raw_result[:1000] + "..."
    return raw_result

# ----------------------------------------------------------------------
# 直接命令處理（複用 tool_handler.process_message）
# ----------------------------------------------------------------------

async def handle_direct_command(user_text: str, user_id: str) -> Optional[str]:
    """
    如果消息以 '/' 開頭，則交給 tool_handler 處理，返回自然化結果。
    若無匹配命令則返回 None。
    """
    if not user_text.startswith('/'):
        return None
    # tool_handler.process_message 返回自然化後的字符串或 None
    result = await tool_handler.process_message(
        user_text=user_text,
        chat_id=user_id,
        ollama_api=OLLAMA_API,
        model_name=MOK_MODEL_NAME,
        cmd_map=tool_handler.get_cmd_map(),
        tools=tool_handler.get_tools()
    )
    return result

# ----------------------------------------------------------------------
# 意圖識別（調用 intent 工具）
# ----------------------------------------------------------------------

async def recognize_intent(user_text: str, user_id: str) -> Tuple[Optional[str], Optional[str]]:
    """
    使用 intent 工具的 handle_intent 邏輯，但這裡我們直接調用其內部函數。
    由於 intent 工具暴露了 handle_intent，但其依賴 Telegram update/context，
    我們重新實現一個輕量版：調用 intent 模塊的 rule_based_intent 和 llm_intent。
    """
    intent_mod = tool_handler.get_tools().get("intent")
    if not intent_mod:
        return None, None
    # 獲取命令映射和工具集
    cmd_map = tool_handler.get_cmd_map()
    tools = tool_handler.get_tools()
    # 規則匹配
    kw_map = intent_mod.build_keyword_map(cmd_map, tools)
    cmd, args = await intent_mod.rule_based_intent(user_text, kw_map)
    if cmd:
        return cmd, args
    # LLM 意圖分類
    cmd, args = await intent_mod.llm_intent(
        user_text, cmd_map, tools, OLLAMA_API, MOK_MODEL_NAME
    )
    return cmd, args

# ----------------------------------------------------------------------
# 多步工作流執行（複用 workflow 工具）
# ----------------------------------------------------------------------

async def execute_multi_step(user_id: str, goal: str, forced_steps: Optional[list] = None) -> Optional[str]:
    """
    多步任務分解與執行。
    如果 forced_steps 提供，則直接執行這些步驟；否則調用 LLM 分解。
    最終返回自然語言總結。
    """
    # 動態導入 workflow 模塊
    workflow_mod = tool_handler.get_tools().get("workflow")
    if not workflow_mod:
        return None

    # 如果有強制步驟，直接執行
    steps = forced_steps
    if not steps:
        # 調用 workflow 的 auto_decompose_goal
        steps = await workflow_mod.auto_decompose_goal(goal)
        if not steps:
            return None

    # 收集執行結果
    collected = []
    cmd_map = tool_handler.get_cmd_map()
    # 構建 tool_schema name -> command 映射
    name_to_cmd = {}
    for mod in tool_handler.get_tools().values():
        if hasattr(mod, "PLUGIN_INFO"):
            info = mod.PLUGIN_INFO
            cmd = info.get("command")
            schema = info.get("tool_schema")
            if cmd and schema and "name" in schema:
                name_to_cmd[schema["name"]] = cmd

    for step in steps:
        tool_name = step.get("name")
        tool_args = step.get("args", "")
        cmd = name_to_cmd.get(tool_name)
        handler = cmd_map.get(cmd) if cmd else None
        if handler:
            try:
                # 規範化參數：admin 可能需要字符串，web_search 可能需要字典
                if tool_name == "admin" and isinstance(tool_args, dict):
                    # 取第一個值作為字符串
                    tool_args = str(next(iter(tool_args.values())))
                elif tool_name == "web_search" and isinstance(tool_args, str):
                    tool_args = {"query": tool_args}
                elif tool_name == "memory" and isinstance(tool_args, dict):
                    # 轉為字符串
                    tool_args = str(next(iter(tool_args.values()))) if tool_args else ""
                # 執行 handler
                raw_result = await handler(tool_args, user_id)
                # 自然化
                naturalized = await naturalize_tool_result(goal, tool_name, raw_result) # 或者傳空字符串
                collected.append(naturalized)
                # 更新工作流進度（如果 workflow 活躍）
                if workflow_mod and hasattr(workflow_mod, "update_step_result"):
                    await workflow_mod.update_step_result(user_id, f"執行 {tool_name} 成功")
            except Exception as e:
                collected.append(f"❌ 工具 {tool_name} 執行失敗: {e}")
        else:
            collected.append(f"❌ 未找到工具 {tool_name}")

    # 總結結果
    summary_prompt = f"用戶目標：{goal}\n\n執行結果：\n" + "\n".join(collected) + "\n\n請用中文像朋友一樣告訴用戶最終結果。"
    final_reply = await call_llm(summary_prompt, stream=False, temperature=0.7, num_predict=1000)
    return final_reply if final_reply else "\n".join(collected)

# ----------------------------------------------------------------------
# 普通聊天（含 Function Calling 工具調用）
# ----------------------------------------------------------------------

async def chat_with_tools(user_id: str, user_text: str, stream_callback: Optional[Callable] = None) -> Optional[str]:
    """
    普通聊天流程：
    1. 檢索相關記憶（若 memory 工具存在）
    2. 構建 prompt（帶工具定義）
    3. 調用 LLM，判斷是否有 tool_call
    4. 若有，執行工具並自然化
    5. 若無，直接返回 LLM 回覆
    """
    # 獲取歷史
    history = get_user_history(user_id)

    # 記憶檢索
    memory_context = ""
    memory_mod = tool_handler.get_tools().get("memory")
    if memory_mod and hasattr(memory_mod, "recall_memory"):
        try:
            recalled = await memory_mod.recall_memory(
                int(user_id) if user_id.isdigit() else user_id,
                user_text,
                MEMORY_RECALL_COUNT,
                include_kb=True
            )
            if recalled:
                memory_context = f"【相關記憶與知識】\n{recalled}\n\n"
        except Exception as e:
            logging.warning(f"記憶檢索失敗: {e}")

    # 構建 prompt
    prompt = memory_context
    for h in history[-MAX_HISTORY_ROUNDS:]:
        prompt += f"用戶:{h['user']}\n{MOK_MODEL_NAME}:{h['assistant']}\n"
    prompt += f"用戶:{user_text}\n{MOK_MODEL_NAME}:"

    # 工具定義
    tool_defs = build_tool_definitions()

    # 調用 LLM
    llm_response = await call_llm(prompt, tools_def=tool_defs, stream=False, temperature=0.2, num_predict=1000)

    # 檢查工具調用
    tool_call = extract_tool_call(llm_response)
    if tool_call:
        tool_name = tool_call.get("name")
        tool_args = tool_call.get("arguments", {})
        handler = find_tool_handler(tool_name)
        if handler:
            # 執行工具
            raw_result = await handler(tool_args, user_id)
            # 自然化
            natural_reply = await naturalize_tool_result(user_text, tool_name, raw_result)
            # 保存歷史
            add_to_history(user_id, user_text, natural_reply)
            return natural_reply
        else:
            error_msg = f"❌ 未找到工具: {tool_name}"
            add_to_history(user_id, user_text, error_msg)
            return error_msg
    else:
        # 普通回覆
        reply = llm_response.strip()
        if not reply:
            reply = "抱歉，我沒有理解你的意思。"
        add_to_history(user_id, user_text, reply)
        return reply

# ----------------------------------------------------------------------
# 統一入口函數
# ----------------------------------------------------------------------

async def process_message(
    user_id: str,
    text: str,
    stream_callback: Optional[Callable[[dict], Awaitable[None]]] = None
) -> Optional[str]:
    """
    處理用戶消息的統一入口。

    :param user_id: 用戶唯一標識（字符串）
    :param text: 用戶輸入文本
    :param stream_callback: 異步回調，接收事件字典：
        - {"type": "think", "content": "..."}  思考過程
        - {"type": "reply", "content": "..."} 回覆片段（流式）
        - {"type": "done"}                    完成
        若不提供，則返回完整字符串。
    :return: 若 stream_callback 為 None，則返回完整回覆；否則返回 None。
    """
    if stream_callback is None:
        # 非流式模式：直接調用各步驟，返回最終字符串
        # 1. 直接命令
        direct_result = await handle_direct_command(text, user_id)
        if direct_result:
            return direct_result
        # 2. 意圖識別
        cmd, args = await recognize_intent(text, user_id)
        if cmd:
            # 執行命令
            cmd_map = tool_handler.get_cmd_map()
            handler = cmd_map.get(cmd)
            if handler:
                raw_result = await handler(args, user_id)
                # 嘗試自然化
                # 獲取工具名
                tool_name = cmd.lstrip('/')
                natural_result = await naturalize_tool_result(text, tool_name, raw_result)
                return natural_result
        # 3. 多步工作流
        workflow_result = await execute_multi_step(user_id, text)
        if workflow_result:
            return workflow_result
        # 4. 普通聊天
        return await chat_with_tools(user_id, text, stream_callback=None)

    # 流式模式：通過回調發送事件
    try:
        # 發送思考開始（可選）
        await stream_callback({"type": "think", "content": "正在思考..."})

        # 1. 直接命令（非流式，但結果一次性發送）
        direct_result = await handle_direct_command(text, user_id)
        if direct_result:
            await stream_callback({"type": "reply", "content": direct_result})
            await stream_callback({"type": "done"})
            return None

        # 2. 意圖識別
        cmd, args = await recognize_intent(text, user_id)
        if cmd:
            cmd_map = tool_handler.get_cmd_map()
            handler = cmd_map.get(cmd)
            if handler:
                raw_result = await handler(args, user_id)
                tool_name = cmd.lstrip('/')
                natural_result = await naturalize_tool_result(text, tool_name, raw_result)
                await stream_callback({"type": "reply", "content": natural_result})
                await stream_callback({"type": "done"})
                return None

        # 3. 多步工作流
        workflow_result = await execute_multi_step(user_id, text)
        if workflow_result:
            await stream_callback({"type": "reply", "content": workflow_result})
            await stream_callback({"type": "done"})
            return None

        # 4. 普通聊天（流式調用 LLM）
        history = get_user_history(user_id)
        memory_context = ""
        memory_mod = tool_handler.get_tools().get("memory")
        if memory_mod and hasattr(memory_mod, "recall_memory"):
            try:
                recalled = await memory_mod.recall_memory(
                    int(user_id) if user_id.isdigit() else user_id,
                    text,
                    MEMORY_RECALL_COUNT,
                    include_kb=True
                )
                if recalled:
                    memory_context = f"【相關記憶與知識】\n{recalled}\n\n"
            except Exception as e:
                logging.warning(f"記憶檢索失敗: {e}")

        prompt = memory_context
        for h in history[-MAX_HISTORY_ROUNDS:]:
            prompt += f"用戶:{h['user']}\n{MOK_MODEL_NAME}:{h['assistant']}\n"
        prompt += f"用戶:{text}\n{MOK_MODEL_NAME}:"

        tool_defs = build_tool_definitions()
        # 使用流式 LLM
        stream_gen = await call_llm(prompt, tools_def=tool_defs, stream=True, temperature=0.7)
        full_reply = ""
        async for token in stream_gen:
            full_reply += token
            await stream_callback({"type": "reply", "content": token})

        # 檢查是否需要工具調用（非流式模式下已在之前處理，流式模式下簡單處理：若回覆為 JSON 則嘗試調用）
        tool_call = extract_tool_call(full_reply)
        if tool_call:
            tool_name = tool_call.get("name")
            tool_args = tool_call.get("arguments", {})
            handler = find_tool_handler(tool_name)
            if handler:
                raw_result = await handler(tool_args, user_id)
                natural_reply = await naturalize_tool_result(text, tool_name, raw_result)
                # 覆蓋之前可能不完整的流式輸出，發送完整自然化結果
                await stream_callback({"type": "reply", "content": "\n\n" + natural_reply})
                full_reply = natural_reply

        if not full_reply:
            full_reply = "抱歉，我沒有理解你的意思。"
            await stream_callback({"type": "reply", "content": full_reply})

        # 保存歷史
        add_to_history(user_id, text, full_reply)
        await stream_callback({"type": "done"})
        return None

    except Exception as e:
        logging.exception("mokagi.process_message 異常")
        error_msg = f"❌ 處理消息時出錯: {str(e)}"
        if stream_callback:
            await stream_callback({"type": "reply", "content": error_msg})
            await stream_callback({"type": "done"})
        return error_msg

# ----------------------------------------------------------------------
# 輔助函數：重新加載工具（供適配器調用）
# ----------------------------------------------------------------------
def reload_tools():
    """重新加載 tools 目錄下的所有插件"""
    tool_handler.load_tools()

# 啟動時加載工具
tool_handler.load_tools()