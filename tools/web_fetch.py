# ------------------------------------------------------------------------------------ #
# 字典: PLUGIN_INFO
# 用途: 定義網頁抓取工具與主程序、意圖識別系統的接口。
# 設計:
#   - naturalize_func 指向 naturalize_fetch_result，讓抓取結果以自然口語呈現。
#   - tool_schema 遵循 JSON Schema 規範，可供 LLM 自動調用。
# ------------------------------------------------------------------------------------ #
PLUGIN_INFO = {
    "command": "/fetch",
    "icon": "🌐",
    "handler": "handle_web_fetch",
    "description": "抓取網頁內容（獲取文本信息）",
    "intent_keywords": [
        ("/取", "/fetch")
    ],
    "updata": "202605171733",
    "naturalize_func": "naturalize_fetch_result",
    "tool_schema": {
        "name": "web_fetch",
        "description": "獲取指定網址的文本內容，返回頁面標題和純文本摘要。",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "要抓取的網頁地址（http:// 或 https://）"
                }
            },
            "required": ["url"]
        }
    }
}




# ---------- 全局導入 ----------
import logging
import html
import json
import time
import os
import re
import httpx
from typing import Union






# ------------------------------------------------------------------------------------ #
# 函數: check_deps
# 用途: 一次性檢查網頁抓取所需的所有依賴庫（trafilatura, markdownify, lxml_html_clean）。
#       若缺少任何一項則返回清晰的安裝指引（附帶複製按鈕），否則返回 None 表示就緒。
# 設計:
#   在 fetch_webpage 一開始呼叫，確保抓取前環境完整。
#   如果檢查失敗，直接回傳錯誤訊息，不執行後續抓取邏輯，避免因缺失庫而崩潰。
#   特別注意 lxml_html_clean 是 trafilatura 的隱藏依賴，需一併檢查。
# 返回:
#   str | None: 若有缺失則回傳錯誤訊息（含安裝指令），否則 None。
# ------------------------------------------------------------------------------------ #
def check_deps():
    """檢查所需庫是否已安裝，返回錯誤信息或 None"""
    missing = []
    try:
        import trafilatura
    except ImportError:
        missing.append("trafilatura")
    try:
        import markdownify
    except ImportError:
        missing.append("markdownify")
    try:
        import httpx
    except ImportError:
        missing.append("httpx")

    if missing:
        missing.append("lxml_html_clean")
        libs = " ".join(missing)
        return f"""❌ 缺少必要庫：{libs}

請執行以下命令安裝：
<pre>/admin pip install {libs}</pre>

完成後請輸入 /reload 重新加載工具。"""
    return None











# ------------------------------------------------------------------------------------ #
# 函數: fetch_webpage
# 用途: 使用 trafilatura 和 markdownify 下載網頁，提取正文並轉換為 Markdown 格式。
# 設計:
#   1. 先呼叫 check_deps() 確保所有依賴就緒，否則直接返回錯誤。
#   2. 自動補全 URL 協議（若缺失則添加 https://）。
#   3. 使用 trafilatura.fetch_url 獲取 HTML 原始內容。
#   4. 提取正文（保留 HTML 格式）或降級為純文本。
#   5. 使用 markdownify 將 HTML 正文轉換為 Markdown，保留標題、鏈接等結構。
#   6. 提取網頁標題（優先使用 trafilatura 的元數據，備用 <title> 標籤）。
#   7. 清理多餘空白和空行，並按 max_chars 截斷過長內容。
# 參數:
#   url: 目標網頁的 URL 字串。
#   max_chars: 最大返回字符數，預設 4000，防止輸出過長。
# 返回:
#   dict: 包含 success, title, content, url, error 等欄位的字典。
# ------------------------------------------------------------------------------------ #
async def fetch_webpage(url: str, max_chars: int = 4000) -> dict:
    """
    使用 trafilatura 下載網頁，提取正文並轉換為 Markdown。
    :param url: 網頁地址
    :param max_chars: 最大返回字符數（避免過長）
    :return: dict { success, title, content, url, error }
    """

    # 先檢查依賴，未安裝則直接返回錯誤信息
    deps_error = check_deps()
    if deps_error:
        return {"success": False, "error": deps_error}

    # 依賴已滿足，此時才導入（確保安裝後可用）
    import trafilatura
    from markdownify import markdownify as md

    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    try:
        # 1. 下載 HTML（trafilatura 處理重定向、編碼等）
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return {"success": False, "error": "無法下載網頁內容，可能是網絡問題或網站拒絕訪問。"}

        # 2. 提取正文（保留基本格式的 HTML）
        main_html = trafilatura.extract(
            downloaded,
            include_formatting=True,   # 保留 <p>, <br> 等標籤，便於轉 Markdown
            include_links=True,        # 保留超連結
            include_images=False,      # 忽略圖片，只取文字
            output_format='html'       # 輸出 HTML 片段
        )

        if not main_html:
            # 降級：嘗試提取純文本
            main_text = trafilatura.extract(downloaded, include_formatting=False)
            if main_text:
                # 純文本直接作為內容（無需轉 Markdown）
                content = main_text
            else:
                return {"success": False, "error": "無法提取網頁正文（可能頁面為空或全是廣告）"}
        else:
            # 3. 將 HTML 轉為 Markdown
            # 使用 markdownify，設定標題樣式、鏈接格式等
            # 可選參數：heading_style="ATX", bullets="-", 等
            content = md(main_html, heading_style="ATX", bullets="-")

        # 4. 提取標題（優先使用 trafilatura 的元數據）
        title = trafilatura.extract(downloaded, include_formatting=False, output_format='txt')
        if title:
            # 取第一行作為標題
            title = title.split('\n')[0].strip()
        if not title:
            # 備用：從 HTML 提取 title 標籤
            title_match = re.search(r'<title[^>]*>(.*?)</title>', downloaded, re.IGNORECASE | re.DOTALL)
            title = title_match.group(1).strip() if title_match else "無標題"

        # 5. 清理內容（移除多餘空行，壓縮空白）
        content = re.sub(r'\n\s*\n', '\n\n', content)  # 保留段落間空行
        content = re.sub(r'[ \t]+', ' ', content)      # 壓縮行內空格
        content = content.strip()

        # 6. 截斷過長內容
        if len(content) > max_chars:
            content = content[:max_chars] + "\n\n... (內容過長，已截斷)"

        return {
            "success": True,
            "title": title,
            "content": content,
            "url": url
        }

    except httpx.TimeoutException:
        return {"success": False, "error": "請求超時，網站響應過慢。"}
    except httpx.HTTPStatusError as e:
        return {"success": False, "error": f"HTTP 錯誤: {e.response.status_code}"}
    except Exception as e:
        logging.exception("網頁抓取異常")
        return {"success": False, "error": f"抓取失敗: {str(e)}"}






















# ------------------------------------------------------------------------------------ #
# 函數: naturalize_fetch_result
# 用途: 將 fetch_webpage 返回的 JSON 結果轉換為口語化的繁體中文回覆。
# 設計:
#   1. 解析 JSON，若抓取失敗則直接返回錯誤訊息。
#   2. 取出標題、前 800 字內容，交給 LLM 生成 1-2 句總結。
#   3. 若 LLM 呼叫成功，返回「標題 + 總結 + 連結」的格式。
#   4. 若 LLM 失敗，降級返回「標題 + 前 300 字純文本預覽 + 連結」。
# 參數:
#   user_text: 使用者原始輸入（保留未使用，但簽名需匹配主程式）。
#   raw_result: fetch_webpage 返回的 JSON 字串。
#   ollama_api: Ollama API 端點，用於生成總結。
#   model_name: 使用的模型名稱。
#   temp_msg, context: 用於流式更新（此函數未實現流式，保留接口）。
# 返回:
#   str: 自然語言結果，可直接展示給使用者。
# ------------------------------------------------------------------------------------ #
async def naturalize_fetch_result(user_text: str, raw_result: str, ollama_api: str, model_name: str, temp_msg=None, context=None) -> str:
    """
    將 JSON 抓取結果轉為自然口語回覆。
    """
    try:
        data = json.loads(raw_result)
    except:
        return raw_result
    if not data.get("success"):
        return f"❌ 無法讀取網頁：{data.get('error', '未知錯誤')}"
    title = data.get("title", "無標題")
    content = data.get("content", "")
    # 限制內容長度，避免模型 token 過多
    preview = content[:800]
    # 讓 LLM 將內容總結為1-2句話
    prompt = f"""用戶想要了解網頁內容：
網址：{data['url']}
標題：{title}
正文摘要（前800字）：
{preview}

請用一句或兩句話告訴用戶這個網頁主要講了什麼。不要提及“根據摘要”，直接說出核心信息。"""
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(ollama_api, json={
                "model": model_name,
                "prompt": prompt,
                "stream": False,
                "options": {"num_predict": 150, "temperature": 0.3}
            })
            summary = resp.json().get("response", "").strip()
            if summary:
                return f"📄 **{title}**\n{summary}\n\n🔗 {data['url']}"
    except:
        pass
    # 備用：直接返回標題和鏈接
    return f"📄 **{title}**\n{content[:300]}\n\n🔗 {data['url']}"
























# ------------------------------------------------------------------------------------ #
# 函數: handle_web_fetch
# 用途: 網頁抓取工具的總入口，負責解析參數、呼叫核心抓取函數、返回 JSON 結果。
# 設計:
#   1. 無參數時顯示幫助訊息（含自然語言觸發詞）。
#   2. 支援兩種輸入格式：命令列字串（"/fetch https://..."）與字典（JSON 工具呼叫）。
#   3. 提取 URL 後直接呼叫 fetch_webpage，並將其返回值轉為 JSON 字串返回。
#   注意：依賴檢查已由 fetch_webpage 內部完成，此處無需重複檢查。
# 參數:
#   args: 可以是字串（直接輸入網址）或字典 {"url": "https://..."}。
#   chat_id: 使用者 ID（此處未使用，保留簽名一致性）。
# 返回:
#   str: JSON 字串，包含 success, title, content, url, error 等欄位。
# ------------------------------------------------------------------------------------ #
async def handle_web_fetch(args: Union[str, dict], chat_id: str = None) -> str:
    """
    處理 /fetch 命令或工具調用。
    args: 可以是字符串（直接輸入網址）或字典 {"url": "https://..."}
    """

    if not args:
        help_text = f'''
{PLUGIN_INFO["icon"]} 取網頁內容說明：
獲取指定網址的文本內容，返回頁面標題和純文本摘要。
<pre>/fetch url</pre>

=====
🧩 自然語言意圖辨識：
'''
        # 動態添加 intent_keywords（不轉義）
        for keyword, cmd in PLUGIN_INFO["intent_keywords"]:
            help_text += f'   "{keyword}" → {cmd}\n'
        return help_text

    if isinstance(args, dict):
        url = args.get("url", "").strip()
    else:
        url = args.strip()


    result = await fetch_webpage(url)
    return json.dumps(result, ensure_ascii=False)


