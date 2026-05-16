# ------------------------------------------------------------------------------------ #
# 字典: PLUGIN_INFO
# 用途: 定義工作流管理工具與主程式、意圖辨識系統之間的介面。
#       主程式透過它來註冊 /workflow 命令、建立自然語言關鍵詞映射、
#       提供給 LLM 的工具描述，以及可選的結果自然化函數。
# 欄位說明:
#   command           : Telegram 命令 "/workflow"，顯示於菜單。
#   icon              : 命令圖示。
#   handler           : 處理函數名稱 "handle_workflow"。
#   description       : 簡短描述，用於命令選單。
#   intent_keywords   : 自然語言觸發詞列表，元組格式（關鍵詞, 完整命令）。
#   naturalize_func   : 結果自然化函數名（此工具未實現，直接返回原始結果）。
#   tool_schema       : 提供給 LLM 的工具定義，描述參數與用途。
# ------------------------------------------------------------------------------------ #
PLUGIN_INFO = {
    "command": "/workflow",
    "icon": "📋",
    "handler": "handle_workflow",
    "description": "管理多步驟任務（創建、繼續、查看、完成）",
    "intent_keywords": [
        ("/工", "/workflow create"),
        ("/工單", "/workflow list"),
        ("/換工", "/workflow switch"),
        ("/進度", "/workflow status"),
        ("/再工", "/workflow resume"),
        ("/完工", "/workflow close")
    ],
    #"naturalize_func": "naturalize_workflow_result",
    "tool_schema": {
        "name": "workflow",
        "description": "管理長期工作流，記錄目標和進度",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create", "resume", "status", "close", "update_step"],
                    "description": "要執行的操作"
                },
                "goal": {"type": "string", "description": "最終目標（create時使用）"},
                "steps": {"type": "array", "description": "步驟列表（可選）"},
                "step_result": {"type": "string", "description": "步驟執行結果（update_step時使用）"}
            },
            "required": ["action"]
        }
    },
    "updata":"202605170422"
}
















import os, json, time, html, httpx
from datetime import datetime
from typing import Optional, Dict, Any



# ------------------------------------------------------------------------------------ #
# 函數: load_agent_config_value
# 用途: 從當前 agent 的配置文件中讀取指定 key 的值。
# 設計:
#   利用環境變數 AD_MOK_AGENT_NAME 和 AD_AgiName 找到配置檔路徑。
#   逐行掃描，支援註解 (#) 和 key=value 格式，不回傳多餘空格。
#   若找不到則回空字串。
# 參數:
#   key: 要讀取的設定鍵名。
# 返回:
#   str: 找到的值，若無則返回空字串。
# ------------------------------------------------------------------------------------ #
def load_agent_config_value(key: str) -> str:
    MOK_AGENT_NAME = os.environ.get("AD_MOK_AGENT_NAME", "")
    if not MOK_AGENT_NAME:
        return ""
    mokagi_name = os.environ.get("AD_AgiName", "MokAgi")
    config_path = os.path.join(os.path.expanduser("~"), f".{mokagi_name}", f".{MOK_AGENT_NAME}")
    if not os.path.exists(config_path):
        return ""
    try:
        with open(config_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    if k.strip() == key:
                        return v.strip()
    except Exception:
        pass
    return ""

# ------------------------------------------------------------------------------------ #
# 函數: get_workflow_root
# 用途: 獲取當前 agent 的工作流根目錄。
# 設計:
#   目錄結構為 ~/.{mokagi_name}/{MOK_AGENT_NAME}/workflows。
#   使用環境變數 AD_AgiName 和 AD_MOK_AGENT_NAME 動態組合。
# 返回:
#   str: 工作流根目錄的絕對路徑。
# ------------------------------------------------------------------------------------ #
def get_workflow_root() -> str:
    """獲取當前 agent 的工作流根目錄：~/.{mokagi_name}/{MOK_AGENT_NAME}/workflows"""
    mokagi_name = os.environ.get("AD_AgiName", "MokAgi")
    MOK_AGENT_NAME = os.environ.get("AD_MOK_AGENT_NAME", "default")
    return os.path.expanduser(f"~/.{mokagi_name}/{MOK_AGENT_NAME}/workflows")

# ------------------------------------------------------------------------------------ #
# 函數: _ensure_dir
# 用途: 為每個使用者建立獨立的工作流目錄。
# 設計:
#   在 get_workflow_root() 下以 chat_id 字串建立子目錄。
#   若目錄已存在則不重複建立。
# 參數:
#   chat_id: 使用者的 Telegram ID（轉為字串）。
# 返回:
#   str: 該使用者的工作流目錄絕對路徑。
# ------------------------------------------------------------------------------------ #
def _ensure_dir(chat_id: str) -> str:
    """為每個用戶創建工作流目錄"""
    user_dir = os.path.join(get_workflow_root(), str(chat_id))
    os.makedirs(user_dir, exist_ok=True)
    return user_dir


# ------------------------------------------------------------------------------------ #
# 函數: auto_decompose_goal
# 用途: 使用 LLM 將使用者目標自動分解為一系列可執行的工具呼叫步驟。
# 設計:
#   動態從主程式獲取所有工具的 tool_schema 定義，構建 prompt 讓 LLM 輸出 JSON 陣列。
#   每個步驟包含 name（工具名）和 args（參數）。
#   若 LLM 分解失敗，返回一個預設的錯誤步驟（執行 echo 提示）。
# 參數:
#   goal: 使用者輸入的任務目標字串。
# 返回:
#   list: 步驟列表，如 [{"name": "admin", "args": "read_file intent.py 20"}]
# ------------------------------------------------------------------------------------ #
async def auto_decompose_goal(goal: str) -> list:
    import __main__
    # 從主程序獲取工具定義
    tool_defs = []
    if hasattr(__main__, 'build_tool_definitions'):
        tool_defs = __main__.build_tool_definitions()

    ollama_api = load_agent_config_value("MOK_MODEL_api") or "http://localhost:11434/api/generate"
    model_name = load_agent_config_value("MOK_MODEL_NAME") or "qwen3:1.7b"

    prompt = f"""你是一個任務分解專家。用戶的目標是：「{goal}」

請將目標分解為一系列**可執行的動作**，每個動作用 JSON 對象表示，包含 "name" 和 "args" 字段。
可用的工具包括：
{tool_defs}

輸出格式：一個 JSON 數組，例如：
[
  {{"name": "admin", "args": "exec cat ~/.MokAgi/tools/memory.py | head -20"}}
]

只輸出 JSON 數組，不要有其他文字。"""
    print(f"👼tools_desc=:\n{tool_defs}\n---------")
    print(f"👼auto_decompose_goal:\n{prompt}\n---------")
    
    async with httpx.AsyncClient(timeout=180) as client:
        resp = await client.post(ollama_api, json={
            "model": model_name,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.3, "num_predict": 500}
        })
        text = resp.json().get("response", "").strip()
        start = text.find('[')
        end = text.rfind(']') + 1
        if start != -1 and end > start:
            try:
                steps = json.loads(text[start:end])
                if isinstance(steps, list):

                    # 規範化參數：確保 admin 的 args 是字符串
                    for step in steps:
                        if step.get("name") == "admin" and isinstance(step.get("args"), dict):
                            # 提取字典中的第一個值作為字符串
                            first_val = next(iter(step["args"].values()))
                            step["args"] = str(first_val)
                    return steps

            except:
                pass
    # 失敗時返回一個默認的 admin exec 步驟（嘗試讀取文件）
    return [{"name": "admin", "args": f"exec echo '無法分解任務，請手動處理'"}]








# ------------------------------------------------------------------------------------ #
# 函數: get_current_workflow
# 用途: 獲取當前使用者未完成的工作流（最新的一個）。
# 設計:
#   優先檢查是否有激活的工作流（.active 檔案），若存在且未完成則返回該工作流資料。
#   否則掃描使用者目錄下所有未歸檔 (非 archived_ 開頭) 且 completed==False 的 JSON 檔案，
#   按 created_at 降序返回最新的。
# 參數:
#   chat_id: 使用者 Telegram ID。
# 返回:
#   Optional[Dict]: 工作流資料字典，若無則返回 None。
# ------------------------------------------------------------------------------------ #
def get_current_workflow(chat_id: str) -> Optional[Dict[str, Any]]:
    """獲取當前未完成的工作流（最新的一個）"""
    user_dir = _ensure_dir(chat_id)
    # 檢查是否有激活的 workflow
    active_path = os.path.join(user_dir, ".active")
    active_id = None
    if os.path.exists(active_path):
        with open(active_path, "r") as f:
            active_id = f.read().strip()
        if active_id:
            path = os.path.join(user_dir, f"{active_id}.json")
            if os.path.exists(path):
                with open(path, "r") as f:
                    data = json.load(f)
                    if not data.get("completed", False):
                        return data
    # 否則返回最新的
    workflows = []
    for fname in os.listdir(user_dir):
        if fname.endswith(".json") and not fname.startswith("archived_"):
            path = os.path.join(user_dir, fname)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if not data.get("completed", False):
                        workflows.append((data.get("created_at", 0), data, path))
            except:
                continue
    if not workflows:
        return None
    workflows.sort(key=lambda x: x[0], reverse=True)  # 最新的優先
    return workflows[0][1]  # 返回 data
# ------------------------------------------------------------------------------------ #
# 函數: create_workflow
# 用途: 創建一個新的工作流，保存為 JSON 檔案，並生成人類可讀的 report.md。
# 設計:
#   工作流 ID 使用當前時間戳（秒）。資料結構包含目標、步驟列表、當前進度、歷史記錄等。
#   同時呼叫 _write_markdown_report 生成便於人工查看的報告。
# 參數:
#   chat_id: 使用者 ID。
#   goal: 最終目標字串。
#   steps: 步驟列表（預設空列表）。
#   mode: 工作流模式（如 "step", "auto"），記錄用。
# 返回:
#   str: 工作流 ID。
# ------------------------------------------------------------------------------------ #
def create_workflow(chat_id: str, goal: str, steps: list = None, mode: str = "step") -> str:
    """創建工作流，返回工作流ID和路徑"""
    user_dir = _ensure_dir(chat_id)
    flow_id = str(int(time.time()))
    data = {
        "flow_id": flow_id,
        "goal": goal,
        "steps": steps or [],
        "current_step": 0,
        "history": [],          # 記錄每一步的結果
        "created_at": time.time(),
        "last_updated": time.time(),
        "completed": False,
        "mode": mode
    }
    path = os.path.join(user_dir, f"{flow_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    # 同時生成一個人類可讀的 report.md
    _write_markdown_report(data, user_dir)
    return flow_id
# ------------------------------------------------------------------------------------ #
# 函數: _write_markdown_report
# 用途: 為工作流生成 Markdown 格式的報告，便於人工查看進度和歷史。
# 設計:
#   輸出標題、最終目標、當前步驟、步驟列表（帶狀態圖標）、執行記錄。
#   報告檔案名為 {flow_id}_report.md，存放於使用者工作流目錄。
# 參數:
#   data: 工作流資料字典。
#   user_dir: 使用者工作流目錄。
# ------------------------------------------------------------------------------------ #
def _write_markdown_report(data: dict, user_dir: str):
    """生成 report.md 方便人工查看"""
    lines = [
        f"# 工作流 {data['flow_id']}",
        f"**最終目標**：{data['goal']}",
        f"**當前步驟**：{data['current_step']}/{len(data['steps'])}",
        "## 步驟列表"
    ]
    for i, step in enumerate(data['steps']):
        status = "✅" if i < data['current_step'] else "⏳" if i == data['current_step'] else "📌"
        lines.append(f"{status} {i+1}. {step}")
    if data['history']:
        lines.append("## 執行記錄")
        for h in data['history']:
            lines.append(f"- 步驟{h['step']}: {h['result'][:100]}")
    markdown_path = os.path.join(user_dir, f"{data['flow_id']}_report.md")
    with open(markdown_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

# ------------------------------------------------------------------------------------ #
# 函數: update_step_result
# 用途: 更新當前步驟的執行結果，並自動推進到下一步。
# 設計:
#   將結果記錄到 history 中，current_step 加一。若已完成所有步驟則標記 completed=True。
#   更新 JSON 檔案和 report.md。
# 參數:
#   chat_id: 使用者 ID。
#   result: 步驟執行結果字串。
# 返回:
#   Optional[str]: 若成功則返回狀態訊息（"已完成" 或 "已記錄並進入下一步"），否則返回 None。
# ------------------------------------------------------------------------------------ #
async def update_step_result(chat_id: str, result: str) -> Optional[str]:
    """更新當前步驟的結果，並推進到下一步"""
    wf = get_current_workflow(chat_id)
    if not wf:
        return None
    steps = wf.get("steps", [])
    cur = wf.get("current_step", 0)
    if cur >= len(steps):
        return None
    # 記錄結果
    wf.setdefault("history", []).append({
        "step": cur,
        "step_desc": steps[cur],
        "result": result,
        "timestamp": time.time()
    })
    # 推進
    wf["current_step"] = cur + 1
    wf["last_updated"] = time.time()
    if wf["current_step"] >= len(steps):
        wf["completed"] = True
    # 寫迴文件
    user_dir = _ensure_dir(chat_id)
    path = os.path.join(user_dir, f"{wf['flow_id']}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(wf, f, ensure_ascii=False, indent=2)
    _write_markdown_report(wf, user_dir)
    return wf["completed"] and "已完成" or "已記錄並進入下一步"
# ------------------------------------------------------------------------------------ #
# 函數: close_workflow
# 用途: 強制歸檔當前工作流（標記為完成並移動檔案）。
# 設計:
#   將 JSON 檔案重新命名為 archived_{flow_id}.json，使其不再被視為進行中。
# 參數:
#   chat_id: 使用者 ID。
# 返回:
#   bool: 成功歸檔返回 True，無活動工作流返回 False。
# ------------------------------------------------------------------------------------ #
def close_workflow(chat_id: str) -> bool:
    """強制歸檔當前工作流"""
    wf = get_current_workflow(chat_id)
    if not wf:
        return False
    wf["completed"] = True
    user_dir = _ensure_dir(chat_id)
    old_path = os.path.join(user_dir, f"{wf['flow_id']}.json")
    new_path = os.path.join(user_dir, f"archived_{wf['flow_id']}.json")
    os.rename(old_path, new_path)
    return True













# ------------------------------------------------------------------------------------ #
# 函數: handle_workflow
# 用途: 工作流命令的總入口，支援字典參數（LLM 工具調用）和字串參數（Telegram 命令）。
# 設計:
#   根據 action（或子命令）執行對應操作：create, resume, status, update_step, close, list, switch。
#   - create: 呼叫 auto_decompose_goal 分解目標，創建工作流，返回特殊標記 WORKFLOW_AUTO_EXEC 讓主程式執行。
#   - resume: 返回當前工作流的下一步提示。
#   - status: 顯示當前工作流進度。
#   - update_step: 記錄步驟執行結果並推進。
#   - close: 歸檔工作流。
#   - list: 列出所有進行中的工作流。
#   - switch: 切換活動工作流。
# 參數:
#   args: 可以是 dict（來自 LLM 工具呼叫）或 str（來自 /workflow 命令）。
#   chat_id: 使用者 ID（由主程式傳入）。
# 返回:
#   str 或 tuple: 若需要返回帶按鈕的訊息則回傳 (text, markup)，否則回傳純文字。
# ------------------------------------------------------------------------------------ #
async def handle_workflow(args, chat_id: str = None) -> str:
    # 統一處理 dict 和 str 兩種輸入
    if isinstance(args, dict):
        action = args.get("action")
        if action == "create":
            goal = args.get("goal", "")
            if not goal:
                return "請提供任務目標"
            # 自動調用 LLM 分解步驟
            steps = await auto_decompose_goal(goal)
            flow_id = create_workflow(chat_id, goal, steps, mode="auto")
            
            # 自動開始執行步驟
            if steps:
                # 構建一個“步驟執行計劃”的提示，交給多步規劃
                steps_text = "\n".join([f"{i+1}. {s}" for i, s in enumerate(steps)])
                # 這裡需要調用主程序的 execute_multi_step，但 workflow.py 裡沒有直接引用
                # 所以我們通過一種變通方法：模擬用戶發送一條消息，內容為“按以下步驟執行：”+步驟列表
                # 由於主程序會處理用戶消息，我們可以返回特殊標記，讓主程序識別後執行
                return f"WORKFLOW_AUTO_EXEC:{chat_id}:{goal}:{json.dumps(steps)}"
            else:
                return f"✅ 已創建工作流 {flow_id}\n目標：{goal}\n但未能分解步驟，無法自動執行。"

        elif action == "resume":
            wf = get_current_workflow(chat_id)
            if not wf:
                return "沒有未完成的工作流"
            steps = wf.get("steps", [])
            cur = wf.get("current_step", 0)
            if cur >= len(steps):
                return "當前工作流已完成所有步驟"
            return f"🔄 恢復工作流：{wf['goal']}\n下一步：{steps[cur]}"
        elif action == "status":
            wf = get_current_workflow(chat_id)
            if not wf:
                return "沒有活動的工作流"
            steps = wf.get("steps", [])
            cur = wf.get("current_step", 0)
            return f"📋 當前任務：{wf['goal']}\n進度：{cur}/{len(steps)}"
        elif action == "update_step":
            step_result = args.get("step_result", "")
            if not step_result:
                return "缺少 step_result"
            result = await update_step_result(chat_id, step_result)
            return f"✅ {result}" if result else "無活動工作流或已無下一步"
        elif action == "close":
            if close_workflow(chat_id):
                return "✅ 已關閉當前工作流"
            else:
                return "沒有活動的工作流"

        elif action == "list":
            user_dir = _ensure_dir(chat_id)
            flows = []
            for fname in os.listdir(user_dir):
                if fname.endswith(".json") and not fname.startswith("archived_"):
                    path = os.path.join(user_dir, fname)
                    with open(path, "r") as f:
                        data = json.load(f)
                        completed = data.get("completed", False)
                        if not completed:
                            flows.append((data.get("created_at", 0), data["goal"], data["flow_id"]))
            if not flows:
                return "沒有進行中的工作流。"
            flows.sort(key=lambda x: x[0])
            lines = ["📋 進行中的工作流："]
            for ts, goal, fid in flows:
                lines.append(f"- {fid}: {goal[:30]}...")
            lines.append("\n使用 /workflow switch <id> 切換活動工作流")
            return "\n".join(lines)
        elif action == "switch":
            new_id = args.get("target_id", "")
            if not new_id:
                return "請提供工作流 ID"
            user_dir = _ensure_dir(chat_id)
            path = os.path.join(user_dir, f"{new_id}.json")
            if not os.path.exists(path):
                return f"工作流 {new_id} 不存在。"
            active_path = os.path.join(user_dir, ".active")
            with open(active_path, "w") as f:
                f.write(new_id)
            return f"✅ 已切換到工作流 {new_id}"






        else:
            return f"未知操作: {action}"
    else:
      if not chat_id:
          return "無法識別用戶"
      # 簡單的命令行解析，也可以解析 JSON
      parts = args.strip().split()
      if not parts:
          help_text = f'''
{PLUGIN_INFO["icon"]} 多步驟任務說明：

    創建工作流 <pre>/workflow create 幫我讀取 memory.py 前20行</pre>

    查看工作流<pre>/workflow status</pre>

    恢復工作流(自動無需操作)<pre>/workflow resume</pre>

    結束工作流<pre>/workflow close</pre>

=====
🧩 自然語言意圖辨識：
'''
          # 動態添加 intent_keywords（不轉義）
          for keyword, cmd in PLUGIN_INFO["intent_keywords"]:
              help_text += f'   "{keyword}" → {cmd}\n'
          return help_text







      action = parts[0].lower()
      if action == "create":
          goal = " ".join(parts[1:])
          if not goal:
              return "請提供任務目標，例如 /workflow create 幫我讀取 memory.py 前20行"
          steps = await auto_decompose_goal(goal)
          flow_id = create_workflow(chat_id, goal, steps, mode="auto")
          # 直接返回自動執行標記
          return f"WORKFLOW_AUTO_EXEC:{chat_id}:{goal}:{json.dumps(steps)}"
      elif action == "resume":
          wf = get_current_workflow(chat_id)
          if not wf:
              return "沒有未完成的工作流。可使用 /workflow create 創建新任務。"
          steps = wf.get("steps", [])
          cur = wf.get("current_step", 0)
          if cur >= len(steps):
              return "當前工作流已完成所有步驟。使用 /workflow close 歸檔。"
          next_step = steps[cur]
          return f"🔄 恢復工作流：{wf['goal']}\n下一步需要：{next_step}\n請繼續。"
      elif action == "status":
          wf = get_current_workflow(chat_id)
          if not wf:
              return "沒有活動的工作流。"
          steps = wf.get("steps", [])
          cur = wf.get("current_step", 0)
          return f"📋 當前任務：{wf['goal']}\n進度：{cur}/{len(steps)}\n下一步：{steps[cur] if cur < len(steps) else '無'}"

      elif action == "update_step":
          step_result = " ".join(parts[1:]) if len(parts) > 1 else ""
          if not step_result:
              return "請提供步驟結果，例如：/workflow update_step 已讀取前20行"
          result = await update_step_result(chat_id, step_result)
          if result is None:
              return "沒有進行中的工作流，或已無下一步。"
          return f"✅ {result}"

      elif action == "close":
          if close_workflow(chat_id):
              return "✅ 已關閉當前工作流。"
          else:
              return "沒有活動的工作流。"
          
      elif action == "list":
          user_dir = _ensure_dir(chat_id)
          flows = []
          for fname in os.listdir(user_dir):
              if fname.endswith(".json") and not fname.startswith("archived_"):
                  path = os.path.join(user_dir, fname)
                  with open(path, "r") as f:
                      data = json.load(f)
                      completed = data.get("completed", False)
                      if not completed:
                          flows.append((data.get("created_at", 0), data["goal"], data["flow_id"]))
          if not flows:
              return "沒有進行中的工作流。"
          flows.sort(key=lambda x: x[0])
          lines = ["📋 進行中的工作流："]
          for ts, goal, fid in flows:
              lines.append(f"- {fid}: {goal[:30]}...")
          lines.append("\n使用 /workflow switch id 切換活動工作流")
          return "\n".join(lines)

      elif action == "switch":
          if len(parts) < 2:
              return "請提供工作流 ID，例如 /workflow switch 1778269327"
          new_id = parts[1]
          user_dir = _ensure_dir(chat_id)
          path = os.path.join(user_dir, f"{new_id}.json")
          if not os.path.exists(path):
              return f"工作流 {new_id} 不存在。"
          active_path = os.path.join(user_dir, ".active")
          with open(active_path, "w") as f:
              f.write(new_id)
          return f"✅ 已切換到工作流 {new_id}"

      else:
          return "未知操作。"




# ------------------------------------------------------------------------------------ #
# 函數: naturalize_workflow_result
# 用途: 工作流結果的自然化函數（佔位）。
# 設計: 本工具未實現自然化，直接返回原始結果。
# 參數:
#   與標準 naturalize_func 簽名相同。
# 返回:
#   str: 原始結果。
# ------------------------------------------------------------------------------------ #
async def naturalize_workflow_result(user_text, raw_result, ollama_api, model_name, temp_msg=None, context=None):
    return raw_result   # 直接返回原始結果