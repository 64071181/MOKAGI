"""
202605250320
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
import openai  # 用於 GitHub Models API
from collections import defaultdict
from typing import Dict, List, Optional, Callable, Awaitable, Any, Tuple, Union, AsyncGenerator

import httpx

# 導入工具管理模塊（獨立於前端）
import tool_handler, recovery

# 設置環境變量，放在所有導入之前
MOKAGI_home = "mok"
os.environ["MOKAGI_HOME"] = MOKAGI_home

# 模型回應的最大等待時間（秒），超過則認定為失敗，避免用戶長時間等待
_model_timeout = 300.0

# 確保工具目錄在 Python 路徑中
TOOLS_DIR = os.path.expanduser(f"~/.{MOKAGI_home}/tools")
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)


# 回覆內容末尾追加模型標籤
def get_model_tag() -> str:
    return f"\n\n---\n🧠 當前模型: {MOK_MODEL_NAME}"




# 按 Agent 隔離
def _get_pending_key(user_id: str) -> str:
      # 刷新全局缓存
    return f"{user_id}_{MOK_AGENT_NAME}"


# ----------------------------------------------------------------------
# 配置加載（從環境變量或 agent 專屬配置文件）
# ----------------------------------------------------------------------
def load_agent_config(agent_name: str = None) -> Dict[str, str]:
    f"""
    加載當前 agent 的配置（通常位於 ~/.{MOKAGI_home}/.溟 或通過環境變量指定）
    如果未指定 agent_name，則嘗試從環境變量 MOK_AGENT_NAME 或 PM2 程序名推斷。
    返回配置字典，包含 MOK_MODEL_NAME, MOK_MODEL_url, 各項參數等。
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
            "MOK_MODEL_url": "http://localhost:11434/v1",
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
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, val = line.split('=', 1)
                config[key.strip()] = val.strip()

                #if 'token' in key.lower():
                #    print2(f"DEBUG: line {line_num}: '{key}' = '{val[:20] if val else 'EMPTY'}'")

    current_model = config.get("MOK_CURRENT_MODEL")
    if current_model:
        current_model = current_model.strip()
        config["MOK_MODEL_NAME"] = current_model
        suffix = None
        # 优先匹配带后缀的（排除无后缀的 MOK_MODEL_NAME）
        for key, val in config.items():
            if key.startswith("MOK_MODEL_NAME") and key != "MOK_MODEL_NAME" and val == current_model:
                suffix = key.replace("MOK_MODEL_NAME", "")
                break
        # 若没找到带后缀的，再尝试匹配无后缀的
        if suffix is None and config.get("MOK_MODEL_NAME") == current_model:
            suffix = ""
        if suffix is not None:
            # 根据 suffix 构造对应的 api 和 token key
            api_key = f"MOK_MODEL_url{suffix}"
            token_key = f"MOK_MODEL_token{suffix}"
            if api_key in config:
                config["MOK_MODEL_url"] = config[api_key]
            config["MOK_MODEL_token"] = config.get(token_key, "").strip()
        else:
            config["MOK_MODEL_token"] = ""

    return config

# 全局配置（啟動時加載一次）
_agent_config = load_agent_config()
  # 刷新全局缓存
MOK_MODEL_NAME = _agent_config.get("MOK_MODEL_NAME", "qwen3:1.7b")
MOK_AGENT_NAME = _agent_config.get("MOK_AGENT_NAME", "助手")
OLLAMA_API = _agent_config.get("MOK_MODEL_url", "http://localhost:11434/v1")
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




# 等待澄清的意圖（key: user_id, value: {original, question, timestamp}）
_pending_clarify: Dict[str, dict] = {}
# 等待用戶確認的命令（key: user_id, value: {cmd, args, original}）
_pending_confirm: Dict[str, dict] = {}



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
    user_id: str = "",
    system_prompt: str = "",
    stream: bool = False,
    tools_def: Optional[List[dict]] = None,
    **override_options
) -> Union[str, AsyncGenerator[dict, None]]:
    """
    統一的 LLM 調用接口，自動根據配置選擇後端：
    - 如果存在 MOK_MODEL_token 且非空，則使用 GitHub Models (OpenAI 兼容)
    - 否則使用 Ollama
    """

    agent_name = _agent_config.get("MOK_AGENT_NAME")
    ADMIN_NAME = _agent_config.get("ADMIN_NAME") # 用戶名稱
    MOK_AGENT_SPEAKING_STYLE = _agent_config.get("MOK_AGENT_SPEAKING_STYLE") # 語氣風格
    MOK_AGENT_COMMON_LANGUAGE = _agent_config.get("MOK_AGENT_COMMON_LANGUAGE")# 慣用語言


    # 獲取當前模型配置
    token = _agent_config.get("MOK_MODEL_token", "")
    use_openai_api = bool(token)
    
    # 構建消息（OpenAI 格式）
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    
    # 通用參數
    temperature = override_options.get("temperature", OLLAMA_OPTIONS.get("temperature", 0.8))
    max_tokens = override_options.get("num_predict", OLLAMA_OPTIONS.get("num_predict", 8192))
    
    if use_openai_api:
        # 從配置中獲取當前模型的 API 地址（而不是使用全局 OLLAMA_API）
        print("-----\nopenai_api 模型調用\n-----")
        current_api = _agent_config.get("MOK_MODEL_url", "")
        if not current_api:
            raise ValueError("MOK_MODEL_url not set for current model")
        client = openai.AsyncOpenAI(
            api_key=token,
            base_url=current_api,
            default_headers={
                "HTTP-Referer": "https://github.com/64071181/MOKAGI",
                "X-Title": "MOK AGI"
            }
        )
        model_name = _agent_config.get("MOK_MODEL_NAME", "")
        
        if stream:
            async def stream_gen():
                try:
                    response = await client.chat.completions.create(
                        model=model_name,
                        messages=messages,
                        stream=True,
                        tools=tools_def,  # 工具定義直接傳入
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                    async for chunk in response:
                        if chunk.choices and chunk.choices[0].delta.content:
                            yield {"type": "reply", "content": chunk.choices[0].delta.content}
                except Exception as e:
                    logging.exception("GitHub Models 流式調用失敗")
                    yield {"type": "reply", "content": f"❌ 生成失敗: {str(e)}"}
            return stream_gen()
        else:
            # 非流式
            try:
                response = await client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    stream=False,
                    tools=tools_def,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                message = response.choices[0].message
                # 检查是否有工具调用
                if message.tool_calls:
                    # 收集所有工具调用结果
                    results = []
                    for tool_call in message.tool_calls:
                        tool_name = tool_call.function.name
                        tool_args = json.loads(tool_call.function.arguments)
                        handler = find_tool_handler(tool_name)
                        if handler:
                            raw_result = await handler(tool_args, user_id)  # user_id 需要从外部传入，这里临时处理
                            # 自然化结果（需要 user_text，但这里没有，传空字符串）
                            natural = await naturalize_tool_result("", tool_name, raw_result)
                            results.append(natural)
                        else:
                            results.append(f"❌ 未找到工具: {tool_name}")
                    # 返回所有工具执行结果拼接（可根据需要优化）
                    return "\n\n".join(results)
                else:
                    return message.content or ""
            except Exception as e:
                logging.exception("OpenAI 調用失敗")
                return await recovery.handle_llm_error(e)
    
    else:
        # ---------- 原有 Ollama 邏輯 ----------
        print("-----\nlocalhost 模型調用\n-----")
        options = OLLAMA_OPTIONS.copy()
        options.update(override_options)
        full_prompt = (system_prompt + "\n\n" + prompt) if system_prompt else prompt
        if tools_def:
            tools_desc = json.dumps(tools_def, ensure_ascii=False, indent=2)
            full_prompt = (
                f"妳是{agent_name}，是一個{MOK_AGENT_SPEAKING_STYLE}的智能助手，可以調用以下工具來幫助{ADMIN_NAME}。\n"
                f"**重要：僅當{ADMIN_NAME}的訊息中明確表達了要執行某個操作（例如「搜尋」、「記住」、「讀取檔案」、「切換模型」等）時，才輸出工具調用 JSON。**\n"
                f"對於普通的問候、閒聊或沒有明確操作意圖的訊息，請直接用{MOK_AGENT_COMMON_LANGUAGE}自然語言回覆，絕對不要輸出 JSON。\n\n"
                "如果需要調用工具，請只輸出一個 JSON 對象，格式如下：\n"
                '{"name": "工具名稱", "arguments": {...}}\n'
                f"如果不需要調用工具，請直接以{MOK_AGENT_COMMON_LANGUAGE}自然語言回答。\n\n"
                f"可用的工具：{tools_desc}\n\n" + full_prompt
            )
            # full_prompt = "妳是一個善於思考的助手。在回答任何問題之前，請先用自然語言寫出妳的推理過程，然後另起一行輸出最終答案。\n\n" + full_prompt

        payload = {
            "model": MOK_MODEL_NAME,
            "prompt": full_prompt,
            "stream": stream,
            "options": options
        }

        if stream:
            async def stream_gen():
                async with httpx.AsyncClient(timeout=httpx.Timeout(_model_timeout, connect=10.0)) as client:
                    try:
                        async with client.stream("POST", OLLAMA_API, json=payload) as resp:
                            resp.raise_for_status()
                            async for line in resp.aiter_lines():
                                if not line:
                                    continue
                                try:
                                    chunk = json.loads(line)
                                    if 'thinking' in chunk and chunk['thinking']:
                                        yield {"type": "think", "content": chunk['thinking']}
                                    if 'response' in chunk and chunk['response']:
                                        yield {"type": "reply", "content": chunk['response']}
                                    if chunk.get('done'):
                                        break
                                except json.JSONDecodeError:
                                    logging.warning(f"Invalid JSON line: {line[:100]}")
                                    continue
                    except Exception as e:
                        logging.exception("流式生成異常")
                        error_msg = await recovery.handle_llm_error(e)
                        yield {"type": "reply", "content": error_msg}
            return stream_gen()
        else:
            async with httpx.AsyncClient(timeout=httpx.Timeout(_model_timeout, connect=10.0)) as client:
                try:
                    resp = await client.post(OLLAMA_API, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                    return data.get("response", "").strip()
                except Exception as e:
                    logging.exception("LLM 調用異常")
                    return await recovery.handle_llm_error(e)




# ----------------------------------------------------------------------
# 工具調用相關函數（複用 tool_handler，並擴展 Function Calling）
# ----------------------------------------------------------------------

def build_tool_definitions() -> List[dict]:
    schemas = []
    tools_dict = tool_handler.get_tools()
    for name, mod in tools_dict.items():
        if hasattr(mod, "PLUGIN_INFO"):
            if "tool_schema" in mod.PLUGIN_INFO:
                original = mod.PLUGIN_INFO["tool_schema"]
                # 包装成 OpenAI 要求的格式
                wrapped = {
                    "type": "function",
                    "function": original
                }
                schemas.append(wrapped)
            else:
                print(f"  -> 警告: {name}缺少 tool_schema 鍵")
        else:
            print(f"  -> 警告: {name}沒有 PLUGIN_INFO 屬性")
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
            # 增加：檢查工具名稱是否真實存在
            if find_tool_handler(data["name"]) is not None:
                return data
            else:
                logging.warning(f"檢測到不存在的工具名稱: {data['name']}，忽略調用")
                return None
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
    print(f"自然化工具結果: tool={tool_name}, raw_result={raw_result[:100]}...")
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
                    return await recovery.naturalize_tool_result_fallback(user_text, tool_name, raw_result)
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
# 工具調用相關函數
# 1.  / 直接命令處理
#（複用 tool_handler.process_message）
# ----------------------------------------------------------------------
async def handle_direct_command(user_text: str, user_id: str) -> Optional[str]:
    """
    工具調用相關函數
    1.  / 直接命令處理
    複用 tool_handler.process_message
    如果消息以 '/' 開頭，則交給 tool_handler 處理，直接執行工具，並返回自然化結果。
    若無匹配命令則返回 None，並去 2️⃣ 意圖識別 (recognize_intent)。
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
# 工具調用相關函數
# 2. 意圖關鍵詞匹配（intent_keywords）
# 調用 intent 模塊的 rule_based_intent 和 llm_intent。
# 2b. LLM 分類意圖 (intent.py.llm_intent)
# ----------------------------------------------------------------------

async def recognize_intent(user_text: str, user_id: str) -> Tuple[Optional[str], Optional[str]]:
    """
    工具調用相關函數
    2. 意圖關鍵詞匹配（tools/intent_keywords）
    調用 intent 模塊的 rule_based_intent 和 llm_intent。
    例子: 記住 我喜歡喝咖啡 == /memory remember 我喜歡喝咖啡
    若無匹配 =  2b. LLM 分類意圖
    """
    intent_mod = tool_handler.get_tools().get("intent")
    if not intent_mod:
        print("警告: intent 模塊未加載，無法識別意圖")
        return None, None
    # 獲取命令映射和工具集
    cmd_map = tool_handler.get_cmd_map()
    tools = tool_handler.get_tools()
    # 規則匹配
    kw_map = intent_mod.build_keyword_map(cmd_map, tools)
    cmd, args = await intent_mod.rule_based_intent(user_text, kw_map)
    if cmd:
        print(f"規則匹配識別到意圖: cmd={cmd}, args={args}")
        return cmd, args

    """
    工具調用相關函數
    2b. LLM 分類意圖 (intent.py.llm_intent)
    使用 LLM 分類意圖，動態生成 prompt（通用版，不硬編碼任何工具）
    若無匹配 =  3. 多步工作流執行(execute_multi_step)
    """
    # LLM 意圖分類
    cmd, args = await intent_mod.llm_intent(
        user_text, cmd_map, tools, OLLAMA_API, MOK_MODEL_NAME
    )
    #print(f"LLM 意圖識別結果: cmd={cmd}, args={args}")
    return cmd, args

# ----------------------------------------------------------------------
# 多步工作流執行（複用 workflow 工具）
# ----------------------------------------------------------------------

async def execute_multi_step(
    user_id: str,
    goal: str,
    forced_steps: Optional[list] = None,
    stream_callback: Optional[Callable[[dict], Awaitable[None]]] = None
) -> Optional[str]:
    """
    多步任務分解與執行。
    - 如果 forced_steps 提供，則直接使用；否則調用 LLM 分解。
    - 如果 stream_callback 不為 None，則進入流式自動執行模式（每步完成後回調），最終返回 None。
    - 否則（非流式）一次性執行所有步驟並返回最終總結字符串。
    """

    agent_name = _agent_config.get("MOK_AGENT_NAME")
    ADMIN_NAME = _agent_config.get("ADMIN_NAME") # 用戶名稱
    MOK_AGENT_SPEAKING_STYLE = _agent_config.get("MOK_AGENT_SPEAKING_STYLE") # 語氣風格
    MOK_AGENT_COMMON_LANGUAGE = _agent_config.get("MOK_AGENT_COMMON_LANGUAGE")# 慣用語言

    workflow_mod = tool_handler.get_tools().get("workflow")
    if not workflow_mod:
        return None

    # 1. 獲取步驟列表
    steps = forced_steps
    if not steps:
        steps = await workflow_mod.auto_decompose_goal(goal)
        if not steps:
            return None
        # 過濾無效分解
        if len(steps) == 1 and steps[0].get("name") == "admin" and "無法分解任務" in steps[0].get("args", ""):
            return None

    # 2. 流式模式：創建工作流並啟動自動執行器
    if stream_callback is not None:
        # 創建工作流（若尚未存在）
        wf = workflow_mod.get_current_workflow(user_id)
        if not wf or wf.get("completed", False):
            workflow_mod.create_workflow(user_id, goal, steps, mode="auto")
        # 啟動自動執行器（後臺任務，不阻塞）
        asyncio.create_task(workflow_mod.run_workflow(user_id, stream_callback))
        return None   # 流式模式不返回最終字符串

    # 3. 非流式模式：保持原有一次性執行邏輯
    # 收集執行結果
    collected = []
    cmd_map = tool_handler.get_cmd_map()
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
                # 參數規範化（同原有邏輯）
                if tool_name == "admin" and isinstance(tool_args, dict):
                    tool_args = str(next(iter(tool_args.values())))
                elif tool_name == "web_search" and isinstance(tool_args, str):
                    tool_args = {"query": tool_args}
                elif tool_name == "memory" and isinstance(tool_args, dict):
                    tool_args = str(next(iter(tool_args.values()))) if tool_args else ""
                raw_result = await handler(tool_args, user_id)
                naturalized = await naturalize_tool_result(goal, tool_name, raw_result)
                collected.append(naturalized)
                if workflow_mod and hasattr(workflow_mod, "update_step_result"):
                    await workflow_mod.update_step_result(user_id, f"執行 {tool_name} 成功")
            except Exception as e:
                error_detail = await recovery.handle_llm_error(e, {"tool": tool_name, "args": tool_args})
                collected.append(error_detail)
        else:
            collected.append(f"❌ 未找到工具 {tool_name}")

    # 總結結果
    summary_prompt = f"{ADMIN_NAME}目標：{goal}\n\n執行結果：\n" + "\n".join(collected) + f"\n\n請用{MOK_AGENT_COMMON_LANGUAGE}，用{MOK_AGENT_SPEAKING_STYLE}的語氣風格告訴{ADMIN_NAME}最終結果。"
    final_reply = await call_llm(summary_prompt, user_id=user_id, stream=False, temperature=0.7, num_predict=1000)
    if final_reply:
        final_reply += get_model_tag()
    else:
        final_reply = "\n".join(collected) + get_model_tag()

    return final_reply if final_reply else "\n".join(collected)










# ----------------------------------------------------------------------
# 使用 LLM 快速判斷用戶請求是否需要多步工具調用
# ----------------------------------------------------------------------

async def is_multi_step_task(user_text: str) -> bool:
    """使用 LLM 快速判斷用戶請求是否需要多步工具調用"""

    agent_name = _agent_config.get("MOK_AGENT_NAME")
    ADMIN_NAME = _agent_config.get("ADMIN_NAME") # 用戶名稱
    MOK_AGENT_SPEAKING_STYLE = _agent_config.get("MOK_AGENT_SPEAKING_STYLE") # 語氣風格
    MOK_AGENT_COMMON_LANGUAGE = _agent_config.get("MOK_AGENT_COMMON_LANGUAGE")# 慣用語言

    prompt = f"""{ADMIN_NAME}請求：{user_text}

判斷該請求是否需要多個步驟（調用多個工具）才能完成。
- 是：例如:需要(搜索、整理、保存)等多個連續操作。
- 否：只需簡單回覆或單個工具調用。

只輸出「是」或「否」，不要有其他內容。"""

    try:
        response = await call_llm(prompt, user_id="", stream=False, temperature=0.1, num_predict=10)
        response = response.strip().lower()
        return "是" in response or "yes" in response
    except Exception as e:
        print(f"LLM 多步判斷失敗: {e}，使用啟發式回退")
        # 回退到簡單關鍵詞判斷
        multi_step_keywords = ["每個", "所有", "然後", "接著", "整理", "保存", "工作區"]
        return any(kw in user_text for kw in multi_step_keywords)












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

    agent_name = _agent_config.get("MOK_AGENT_NAME")
    ADMIN_NAME = _agent_config.get("ADMIN_NAME") # 用戶名稱
    MOK_AGENT_SPEAKING_STYLE = _agent_config.get("MOK_AGENT_SPEAKING_STYLE") # 語氣風格
    MOK_AGENT_COMMON_LANGUAGE = _agent_config.get("MOK_AGENT_COMMON_LANGUAGE")# 慣用語言

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
        prompt += f"{ADMIN_NAME}:{h['user']}\n{MOK_AGENT_NAME}:{h['assistant']}\n"
    prompt += f"{ADMIN_NAME}:{user_text}\n{MOK_AGENT_NAME}:"

    # 工具定義
    tool_defs = build_tool_definitions()

    print(f"========= 👼{agent_name}普通聊天👼 =========\n{prompt}\n===============================")


    # 調用 LLM
    llm_response = await call_llm(prompt,user_id=user_id, tools_def=tool_defs, stream=False, temperature=0.2, num_predict=1000)

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
            natural_reply += get_model_tag()   # 添加這行
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
            reply = "抱歉，我沒有理解妳的意思。"
        reply += get_model_tag()
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

    agent_name = _agent_config.get("MOK_AGENT_NAME")
    MOK_AGENT_ICON = _agent_config.get("MOK_AGENT_ICON")
    ADMIN_NAME = _agent_config.get("ADMIN_NAME") # 用戶名稱
    MOK_AGENT_SPEAKING_STYLE = _agent_config.get("MOK_AGENT_SPEAKING_STYLE") # 語氣風格
    MOK_AGENT_COMMON_LANGUAGE = _agent_config.get("MOK_AGENT_COMMON_LANGUAGE")# 慣用語言

    # ---------- 0. 處理等待確認的命令 ----------
    pending_confirm = _pending_confirm.get(_get_pending_key(user_id))
    if pending_confirm:

        print(f"========= {MOK_AGENT_ICON}{agent_name}處理等待確認的命令{MOK_AGENT_ICON} =========\npending_confirm：{pending_confirm}\n===============================")

        if text.strip() in ["確認", "是", "yes", "Yes", "YES", "確認", "對"]:
            cmd = pending_confirm["cmd"]
            args = pending_confirm["args"]
            del _pending_confirm[_get_pending_key(user_id)]
            cmd_map = tool_handler.get_cmd_map()
            handler = cmd_map.get(cmd)
            if handler:
                raw_result = await handler(args, user_id)
                tool_name = cmd.lstrip('/')
                natural_result = await naturalize_tool_result(text, tool_name, raw_result)
                final = natural_result + get_model_tag()
                if stream_callback:
                    await stream_callback({"type": "reply", "content": final})
                    await stream_callback({"type": "reply", "content": get_model_tag()})
                    await stream_callback({"type": "done"})
                    return None
                else:
                    return final
            else:
                error_msg = f"❌ 未找到命令: {cmd}"
                if stream_callback:
                    await stream_callback({"type": "reply", "content": error_msg})
                    await stream_callback({"type": "reply", "content": get_model_tag()})
                    await stream_callback({"type": "done"})
                    return None
                else:
                    return error_msg
        else:
            # 用戶取消確認，清空狀態並繼續處理當前消息
            del _pending_confirm[_get_pending_key(user_id)]

    # ---------- 1. 處理等待澄清的意圖 ----------
    pending_clarify = _pending_clarify.get(_get_pending_key(user_id))
    if pending_clarify:

        print(f"========= {MOK_AGENT_ICON}{agent_name}處理等待澄清的意圖{MOK_AGENT_ICON} =========\npending_clarify：{pending_clarify}\n===============================")

        original = pending_clarify["original"]
        question = pending_clarify["question"]
        del _pending_clarify[_get_pending_key(user_id)]
        # 重新理解意圖
        result = await recovery.merge_and_reunderstand(user_id, original, question, text)
        if result:
            cmd, args = result
            confirm_msg = f"{MOK_AGENT_ICON} {agent_name}理解{ADMIN_NAME}的意圖是執行命令：`{cmd}`，參數：`{args}`。\n請回復「確認」以執行，或者回復其他內容重新描述。"
            _pending_confirm[_get_pending_key(user_id)] = {"cmd": cmd, "args": args, "original": original}
            if stream_callback:
                await stream_callback({"type": "reply", "content": confirm_msg})
                await stream_callback({"type": "done"})
            else:
                return confirm_msg
        else:
            msg = f"抱歉，{agent_name}還是無法理解{ADMIN_NAME}的意圖。請重新描述{ADMIN_NAME}您想讓{agent_name}做什麼。"
            if stream_callback:
                await stream_callback({"type": "reply", "content": msg})
                await stream_callback({"type": "done"})
            else:
                return msg
        return None



    if stream_callback is None:
        # 非流式模式：直接調用各步驟，返回最終字符串

        # ------------- 1. 直接命令 -------------
        direct_result = await handle_direct_command(text, user_id)
        if direct_result:
            return direct_result + get_model_tag()

        # ------------- 2. 意圖識別(意圖關鍵詞匹配/LLM 分類意圖) -------------
        cmd, args = await recognize_intent(text, user_id)

        # ------------- 4. 普通聊天 -------------
        if cmd == "chat":
            return await chat_with_tools(user_id, text, stream_callback=None)
        elif cmd:
            # 執行命令
            cmd_map = tool_handler.get_cmd_map()
            handler = cmd_map.get(cmd)
            if handler:
                raw_result = await handler(args, user_id)
                # 嘗試自然化
                # 獲取工具名
                tool_name = cmd.lstrip('/')
                natural_result = await naturalize_tool_result(text, tool_name, raw_result)
                return natural_result + get_model_tag()

        # ------------- 3. 意圖模糊，主動提問 -------------
        question = await recovery.ask_clarification(text)
        _pending_clarify[_get_pending_key(user_id)] = {"original": text, "question": question, "timestamp": time.time()}
        return question + get_model_tag()

        # ------------- 3. 多步任務檢測與執行 -------------
        if await is_multi_step_task(text):
            workflow_result = await execute_multi_step(user_id, text, stream_callback=None)
            if workflow_result:
                return workflow_result


    # 流式模式：一邊生成一邊調用|通過回調發送事件
    try:
        # 發送思考開始（可選）
        await stream_callback({"type": "think", "content": ""})

        # ------------- 1. 直接命令（非流式，但結果一次性發送） -------------
        await stream_callback({"type": "think", "content": f"{MOK_AGENT_ICON}檢查直接命令...\n"})
        direct_result = await handle_direct_command(text, user_id)
        if direct_result:
            await stream_callback({"type": "reply", "content": direct_result})
            await stream_callback({"type": "reply", "content": get_model_tag()})
            await stream_callback({"type": "done"})
            return None

        # ------------- 2. 意圖識別(意圖關鍵詞匹配/LLM 分類意圖) -------------
        await stream_callback({"type": "think", "content": f"{MOK_AGENT_ICON}意圖識別中...\n"})
        cmd, args = await recognize_intent(text, user_id)



        if cmd != "chat":
            cmd_map = tool_handler.get_cmd_map()
            handler = cmd_map.get(cmd)
            if handler:
                raw_result = await handler(args, user_id)
                tool_name = cmd.lstrip('/')
                natural_result = await naturalize_tool_result(text, tool_name, raw_result)

                await stream_callback({"type": "reply", "content": natural_result})
                await stream_callback({"type": "reply", "content": get_model_tag()})
                await stream_callback({"type": "done"})
                return None

            # ------------- 3. 意圖模糊，主動提問 -------------
            question = await recovery.ask_clarification(text)
            _pending_clarify[_get_pending_key(user_id)] = {"original": text, "question": question, "timestamp": time.time()}
            await stream_callback({"type": "think", "content": f"{MOK_AGENT_ICON}意圖模糊...需要更多信息\n"})
            await stream_callback({"type": "reply", "content": question})
            await stream_callback({"type": "reply", "content": get_model_tag()})
            await stream_callback({"type": "done"})
            return None

            '''
            # ------------- 3. 多步任務檢測與執行 -------------
            await stream_callback({"type": "think", "content": "檢測是否多步任務..."})
            if await is_multi_step_task(text):
                workflow_result = await execute_multi_step(user_id, text, stream_callback=stream_callback)
                if workflow_result:   # 流式模式通常返回 None，但保留
                    await stream_callback({"type": "reply", "content": workflow_result})
                    await stream_callback({"type": "done"})
                    return None
            '''

        else:
            # ------------- 4. 普通聊天（流式調用 LLM） -------------
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
                prompt += f"{ADMIN_NAME}:{h['user']}\n{MOK_AGENT_NAME}:{h['assistant']}\n"
            prompt += f"{ADMIN_NAME}:{text}\n{MOK_AGENT_NAME}:"

            tool_defs = build_tool_definitions()
            # 使用流式 LLM
            stream_gen = await call_llm(prompt, user_id=user_id, tools_def=tool_defs, stream=True, temperature=0.7)
            full_reply = ""
            async for item in stream_gen:
                if item["type"] == "think":
                    await stream_callback({"type": "think", "content": item["content"]})
                elif item["type"] == "reply":
                    full_reply += item["content"]
                    await stream_callback({"type": "reply", "content": item["content"]})

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
                full_reply = "抱歉，我沒有理解妳的意思。"
                await stream_callback({"type": "reply", "content": full_reply})

            model_tag = get_model_tag()
            full_reply += model_tag
            await stream_callback({"type": "reply", "content": model_tag})

            # 保存歷史
            add_to_history(user_id, text, full_reply)
            await stream_callback({"type": "done"})
            return None

    except Exception as e:
        logging.exception("mokagi.process_message 異常")
        error_msg = await recovery.handle_llm_error(e, {"stage": "process_message"})
        if stream_callback:
            await stream_callback({"type": "reply", "content": error_msg})
            await stream_callback({"type": "reply", "content": get_model_tag()})
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