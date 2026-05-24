# ------------------------------------------------------------------------------------ #
# 字典: PLUGIN_INFO
# 用途: 定義自動修正工具與主程式、意圖辨識系統之間的介面。
#       主程式透過它來註冊 /autofix 命令、建立自然語言關鍵詞映射、
#       提供給 LLM 的工具描述。
# 欄位說明:
#   command           : Telegram 命令 "/autofix"，顯示於菜單。
#   icon              : 命令圖示。
#   handler           : 處理函數名稱 "handle_autofix"。
#   description       : 簡短描述，用於命令選單。
#   intent_keywords   : 自然語言觸發詞列表（可選）。
#   tool_schema       : 提供給 LLM 的工具定義，描述參數與用途。
# ------------------------------------------------------------------------------------ #

PLUGIN_INFO = {
    "command": "/autofix",
    "icon": "🔧",
    "handler": "handle_autofix",
    "description": "自動修正程式碼錯誤（提供錯誤訊息和程式碼，AI 嘗試生成修正版本）",
    "intent_keywords": [
        ("修正", "/autofix"),
        ("修復", "/autofix"),
        ("除錯", "/autofix"),
        ("debug", "/autofix"),
    ],
    "tool_schema": {
        "name": "autofix",
        "description": "當執行 Python 程式碼失敗時，使用此工具分析錯誤並嘗試提供修正後的程式碼。",
        "parameters": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "原始的程式碼（出錯的程式碼）"
                },
                "error": {
                    "type": "string",
                    "description": "執行程式碼時產生的錯誤訊息（包含 traceback）"
                },
                "context": {
                    "type": "string",
                    "description": "（可選）額外的上下文資訊，例如使用者意圖、預期行為等"
                }
            },
            "required": ["code", "error"]
        }
    },
    "update": "202605250320"
}

import logging
import subprocess
import tempfile
import os
import json
import asyncio
from typing import Optional, Tuple

import mokagi

# ------------------------------------------------------------------------------------ #
# 輔助函數: execute_code_safely
# 用途: 在臨時檔案中執行程式碼，並捕獲輸出和錯誤，超時限制 30 秒。
# 參數:
#   code: 要執行的 Python 程式碼字串。
# 返回:
#   (success, output, error)
#     success: bool 是否執行成功（無未捕獲異常）
#     output: stdout 輸出
#     error: stderr 輸出（如果發生異常則包含 traceback）
# ------------------------------------------------------------------------------------ #
async def execute_code_safely(code: str) -> Tuple[bool, str, str]:
    """在隔離環境中執行 Python 程式碼，返回 (成功與否, stdout, stderr)"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
        f.write(code)
        tmp_path = f.name
    
    try:
        proc = await asyncio.create_subprocess_exec(
            'python3', tmp_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            limit=10*1024*1024  # 10MB 限制
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        success = (proc.returncode == 0)
        return success, stdout.decode('utf-8', errors='replace'), stderr.decode('utf-8', errors='replace')
    except asyncio.TimeoutError:
        return False, "", "執行超時（超過 30 秒）"
    except Exception as e:
        return False, "", str(e)
    finally:
        try:
            os.unlink(tmp_path)
        except:
            pass

# ------------------------------------------------------------------------------------ #
# 函數: generate_fix
# 用途: 呼叫 LLM 分析錯誤並生成修正後的程式碼。
# 參數:
#   original_code: 原始程式碼
#   error_msg: 錯誤訊息
#   context: 額外上下文（可選）
# 返回:
#   (fixed_code, explanation) 或 (None, error_message)
# ------------------------------------------------------------------------------------ #
async def generate_fix(original_code: str, error_msg: str, context: str = "") -> Tuple[Optional[str], str]:
    """讓 LLM 產生修正後的程式碼"""
    prompt = f"""你是一個專業的 Python 開發者。用戶提供的程式碼執行時發生錯誤，請分析錯誤原因並給出修正後的完整程式碼。

原始程式碼：
```python
{original_code}

錯誤訊息：
{error_msg}
```
{f"額外上下文：{context}" if context else ""}

請輸出 JSON 格式，包含以下欄位：

"fixed_code": 修正後的完整程式碼（字串）

"explanation": 簡短的修正說明（一句話）

只輸出 JSON，不要有其他文字。"""

    try:
        response = await mokagi.call_llm(prompt, stream=False, temperature=0.2, num_predict=1500)
        response = response.strip()
        start = response.find('{')
        end = response.rfind('}') + 1
        if start == -1 or end <= start:
          return None, "無法解析 LLM 回應：找不到 JSON"
        data = json.loads(response[start:end])
        fixed = data.get("fixed_code")
        explanation = data.get("explanation", "已產生修正版本")
        if not fixed:
          return None, "LLM 未提供修正程式碼"
        return fixed, explanation
    except Exception as e:
        logging.exception("generate_fix 失敗")
        return None, f"內部錯誤：{str(e)}"

# ------------------------------------------------------------------------------------
# 函數: handle_autofix
# 用途: 工具的主要入口，處理 /autofix 命令或 LLM 工具調用。
# 參數:
# args: 可以是字串（命令行格式 "/autofix <code_and_error>"）或字典（tool call）。
# chat_id: 使用者 ID（用於權限檢查，可選）。
# 返回:
# str: 結果訊息，支援 HTML 格式。
# ------------------------------------------------------------------------------------
async def handle_autofix(args, chat_id: str = None) -> str:

    # 解析參數
    code = ""
    error = ""
    context = ""

    if isinstance(args, dict):
        code = args.get("code", "")
        error = args.get("error", "")
        context = args.get("context", "")
    elif isinstance(args, str):
        lines = args.strip().split('\n')
        traceback_start = -1
        for i, line in enumerate(lines):
            if "Traceback (most recent call last)" in line:
                traceback_start = i
                break
        if traceback_start >= 0:
            code = "\n".join(lines[:traceback_start])
            error = "\n".join(lines[traceback_start:])
        else:
            # 沒有找到 traceback，假設整個輸入就是錯誤信息
            error = args
            code = "(未提供程式碼)"

    if not code or code == "(未提供程式碼)":
        return "❌ 請提供原始程式碼。"
    if not error:
        return "❌ 請提供錯誤訊息。"

    # 產生修正版本
    fixed_code, explanation = await generate_fix(code, error, context)
    if fixed_code is None:
        return f"❌ 無法生成修正程式碼：{explanation}"

    #可選：自動執行修正後的程式碼以驗證（需使用者確認，這裡先不自動執行）
    # 改為提供修正程式碼，讓使用者複製或確認後再執行
    result = f"""🔧 自動修正建議

{explanation}
修正後的程式碼：
```python
{fixed_code}
```
請複製上方程式碼並再次執行。如果需要我自動執行修正後的程式碼。
"""

    # autofix.py - handle_autofix 函數末尾
    if chat_id and is_admin(chat_id):
        from admin import request_confirmation, is_admin   # 導入公共函數
        token = request_confirmation(
            chat_id=chat_id,
            cmd_type="autofix_exec",
            args=fixed_code,
            description="執行自動修正後的 Python 程式碼"
        )
        result += f"\n\n⚠️ 將執行修正後的程式碼，請確認：\n<pre>/admin confirm {token}</pre>"
    else:
        result += "\n\n（非管理員無法執行修正程式碼）"

    return result

# ------------------------------------------------------------------------------------
# 額外功能：處理使用者確認執行修正程式碼
# 這需要掛接到 mokagi.process_message 的確認流程，或者單獨提供一個命令 /confirm_fix
# 但為了最小改動，我們不在本工具中實現完整確認邏輯，僅提供修正建議。
# 如果希望集成確認機制，可以擴展 admin.py 的確認碼機制或使用 _pending_confirm。
# ------------------------------------------------------------------------------------









async def execute_autofix_code(code: str) -> tuple:
    """實際執行修正後的 Python 代碼"""
    from autofix import execute_code_safely
    success, out, err = await execute_code_safely(code)
    if success:
        result = f"✅ 修正代碼執行成功\n輸出：\n{out[:1000]}" if out else "✅ 修正代碼執行成功（無輸出）"
        return True, result
    else:
        return False, f"❌ 執行修正代碼時出錯：\n{err[:1000]}"