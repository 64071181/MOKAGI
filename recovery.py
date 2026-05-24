"""
202605250320
recovery.py - 統一處理意圖模糊、異常恢復等需要 LLM 介入的場景
"""

import json
import logging
import httpx
from typing import Optional, Tuple
import tool_handler


async def ask_clarification(user_text: str) -> str:
    """當無法識別意圖時，讓 LLM 分析{ADMIN_NAME}輸入，指出模糊之處並生成提問"""

    import mokagi  # 延遲導入
    agent_name = mokagi._agent_config.get("MOK_AGENT_NAME")
    ADMIN_NAME = mokagi._agent_config.get("ADMIN_NAME") # {ADMIN_NAME}名稱
    MOK_AGENT_SPEAKING_STYLE = mokagi._agent_config.get("MOK_AGENT_SPEAKING_STYLE") # 語氣風格
    MOK_AGENT_COMMON_LANGUAGE = mokagi._agent_config.get("MOK_AGENT_COMMON_LANGUAGE")# 慣用語言


    prompt = f"""{ADMIN_NAME}說：「{user_text}」
妳是{agent_name}，妳剛剛無法確定{ADMIN_NAME}意圖。請：
1. 分析模糊之處（缺少關鍵詞、動作不明確、對象缺失等）。
2. 生成一個{MOK_AGENT_SPEAKING_STYLE}的{MOK_AGENT_COMMON_LANGUAGE}列表清單，引導{ADMIN_NAME}補充必要信息。

輸出格式：
分析結果\n\n
提問"""

    default_question = f"抱歉{ADMIN_NAME}，{agent_name}無法理解「{user_text[:50]}...」。請補充說明：{ADMIN_NAME}是想讓{agent_name}記住某件事、搜索信息、管理工作流，還是執行其他操作？"
    try:
        reply = await mokagi.call_llm(prompt, stream=False, temperature=0.5, num_predict=200)
        if reply.startswith("❌"):
            # 失敗時嘗試簡化 prompt
            simple_prompt = f"{ADMIN_NAME}說：「{user_text}」。請用一句話直接問{ADMIN_NAME}需要什麼幫助。"
            reply2 = await mokagi.call_llm(simple_prompt, stream=False, temperature=0.3, num_predict=50)
            if reply2.startswith("❌"):
                return default_question
            reply = reply2.strip()
        if not reply or len(reply) < 5:
            return default_question
        return reply.strip()
    except Exception as e:
        logging.warning(f"ask_clarification 異常: {e}")
        return default_question


async def merge_and_reunderstand(user_id: str, original: str, question: str, answer: str) -> Optional[Tuple[str, str]]:

    """將原始輸入、AI提問、{ADMIN_NAME}回答合併，讓LLM重新理解意圖，返回 (cmd, args) 或 None"""

    import mokagi  # 延遲導入
    agent_name = mokagi._agent_config.get("MOK_AGENT_NAME")
    ADMIN_NAME = mokagi._agent_config.get("ADMIN_NAME") # {ADMIN_NAME}名稱
    MOK_AGENT_SPEAKING_STYLE = mokagi._agent_config.get("MOK_AGENT_SPEAKING_STYLE") # 語氣風格
    MOK_AGENT_COMMON_LANGUAGE = mokagi._agent_config.get("MOK_AGENT_COMMON_LANGUAGE")# 慣用語言

    prompt = f"""對話歷史：
- {ADMIN_NAME}原話：{original}
- 我({agent_name})提問：{question}
- {ADMIN_NAME}回答：{answer}

根據上述對話，重新判斷{ADMIN_NAME}意圖，輸出 JSON：
- 如需聊天：{{"command": "chat"}}
- 具體命令：{{"command": "命令", "args": "參數"}}
- 無法確定：{{"command": "none"}}

只輸出 JSON，不要其他內容。"""

    try:
        response = await mokagi.call_llm(prompt, stream=False, temperature=0.2, num_predict=200)
        response = response.strip()
        start = response.find('{')
        end = response.rfind('}') + 1
        if start != -1 and end > start:
            data = json.loads(response[start:end])
            cmd = data.get("command")
            args = data.get("args", "")
            if cmd == "chat":
                return "chat", ""
            if cmd and cmd != "none" and cmd in tool_handler.get_cmd_map():
                return cmd, args
    except Exception as e:
        logging.warning(f"重新理解意圖失敗: {e}")
    return None




 






# 通用錯誤處理函數
async def handle_llm_error(error: Exception, context: dict = None) -> str:
    """處理 LLM 調用中的錯誤，返回{ADMIN_NAME}友好的消息"""

    import mokagi  # 延遲導入
    agent_name = mokagi._agent_config.get("MOK_AGENT_NAME")
    ADMIN_NAME = mokagi._agent_config.get("ADMIN_NAME") # {ADMIN_NAME}名稱
    MOK_AGENT_SPEAKING_STYLE = mokagi._agent_config.get("MOK_AGENT_SPEAKING_STYLE") # 語氣風格
    MOK_AGENT_COMMON_LANGUAGE = mokagi._agent_config.get("MOK_AGENT_COMMON_LANGUAGE")# 慣用語言

    error_type = type(error).__name__
    if isinstance(error, httpx.TimeoutException):
        return "⏰ 模型響應超時，請稍後重試或檢查模型服務是否正常。"
    elif isinstance(error, httpx.HTTPStatusError):
        status = error.response.status_code
        if status == 404:
            return "❌ 模型端點不存在，請檢查配置文件中的 MOK_MODEL_url 是否正確。"
        else:
            return f"❌ HTTP 錯誤 {status}，請檢查網絡或模型服務。"
    else:
        # 讓 LLM 分析錯誤並給出建議
        prompt = f"妳是 {agent_name}，在調用語言模型時遇到錯誤：{error_type}: {str(error)}。請生成一句簡短、{MOK_AGENT_SPEAKING_STYLE}的{MOK_AGENT_COMMON_LANGUAGE}提示。告訴{ADMIN_NAME}，並建議可能的原因（如網絡問題、配置錯誤等）。只輸出提示內容。"
        try:
            reply = await mokagi.call_llm(prompt, stream=False, temperature=0.3, num_predict=100)
            return reply.strip() if reply else f"❌ 生成失敗：{error_type}"
        except:
            return f"❌ 系統錯誤：{error_type}，請聯繫管理員。"
        












async def naturalize_tool_result_fallback(user_text: str, tool_name: str, raw_result: str) -> str:
    """當工具的自然化函數失敗時，讓 LLM 生成一個友好的摘要"""

    import mokagi  # 延遲導入
    agent_name = mokagi._agent_config.get("MOK_AGENT_NAME")
    ADMIN_NAME = mokagi._agent_config.get("ADMIN_NAME") # {ADMIN_NAME}名稱
    MOK_AGENT_SPEAKING_STYLE = mokagi._agent_config.get("MOK_AGENT_SPEAKING_STYLE") # 語氣風格
    MOK_AGENT_COMMON_LANGUAGE = mokagi._agent_config.get("MOK_AGENT_COMMON_LANGUAGE")# 慣用語言

    prompt = f"""{ADMIN_NAME}請求：{user_text}
工具 {tool_name} 返回了原始結果：
{raw_result[:800]}

請用一句簡短、{MOK_AGENT_SPEAKING_STYLE}的{MOK_AGENT_COMMON_LANGUAGE}告訴{ADMIN_NAME}這個結果的核心信息。不要提及“根據結果”，直接說結論。"""
    try:
        reply = await mokagi.call_llm(prompt, stream=False, temperature=0.3, num_predict=100)
        if reply and not reply.startswith("❌"):
            return reply.strip()
    except Exception:
        pass
    # 降級：返回截斷的原始結果
    if len(raw_result) > 500:
        raw_result = raw_result[:500] + "..."
    return f"工具返回：{raw_result}"