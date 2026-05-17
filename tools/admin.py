# ------------------------------------------------------------------------------------ #
# 字典: PLUGIN_INFO
# 用途: 定義管理工具與主程式、意圖辨識系統之間的介面。
#       主程式透過它來註冊 /admin 命令、建立自然語言關鍵詞映射、
#       提供給 LLM 的工具描述，以及指定結果自然化函數。
# 欄位說明:
#   command           : Telegram 命令 "/admin"，顯示於菜單。
#   icon              : 命令圖示。
#   handler           : 處理函數名稱 "handle_admin"。
#   description       : 簡短描述，用於命令選單。
#   intent_keywords   : 自然語言觸發詞列表，元組格式（關鍵詞, 完整命令）。
#   naturalize_func   : 結果自然化函數名 "naturalize_admin_result"。
#   tool_schema       : 提供給 LLM 的工具定義，描述參數與用途。
#   updata            : 最後更新日期。
# ------------------------------------------------------------------------------------ #


PLUGIN_INFO = {
    "command": "/admin",  # 這個命令會出現在 TG 菜單
    "icon":"🤖",
    "handler": "handle_admin",
    "description": "管理工具 (read_file, htop, ollama list, rm, pip install , exec 等)",
    "intent_keywords": [

        ("/讀", "/admin read_file"),

        ("/htop", "/admin htop"),

        ("/cpu", "/admin cpu"),

        ("/模型", "/admin mode"),

        ("/換模型", "/admin set_model "),

        ("/logs", "/admin logs")
    ],
    "naturalize_func": "naturalize_admin_result",
    "tool_schema": {
        "name": "admin",
        "description": "執行系統管理操作，包括查看負載、CPU、模型列表、日誌，切換模型，刪除模型，安裝 pip 包，執行 shell 命令，以及讀取文件。",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["htop", "cpu", "mode", "logs", "set_model", "ollama_rm", "pip", "exec", "read_file"],
                    "description": "要執行的管理操作類型"
                },
                "args": {
                    "type": "string",
                    "description": "操作參數，例如 set_model 後的模型名，pip install 後的包名，exec 後的 shell 命令，read_file 後的文件路徑和行數（如 \"intent.py 20\"）"
                }
            },
            "required": ["action"]
        }
    },
    "updata":"202605171733"
}

import os, logging, html, time, hashlib, subprocess, json, httpx


mokagi_name = os.environ.get("AD_AgiName")
agent_name = os.environ.get("AD_MOK_AGENT_NAME")





# ------------------------------------------------------------------------------------ #
# 輔助函數: get_config_file_path
# 用途: 返回當前 agent 的配置文件路徑。
# 設計:
#   根據環境變數 AD_AgiName 和 AD_MOK_AGENT_NAME 組合路徑 ~/.{mokagi_name}/.{agent_name}。
#   若 agent_name 不存在則返回 None。
# 返回:
#   str | None: 配置文件路徑或 None。
# ------------------------------------------------------------------------------------ #
def get_config_file_path():
    """返回當前 agent 的配置文件路徑（如 ~/.MokAgi/.溟）"""
    if not agent_name:
        return None
    config_path = os.path.join(os.path.expanduser(f"~/.{mokagi_name}"), f".{agent_name}")
    return config_path if os.path.exists(config_path) else None

















'''
                      .                                -                        
                      #%.                             =@@%.                     
                       @@-                            @@#*                      
                       =@@                           *@@ .#                     
            :.          @@         .:               :@@.  +*                    
            -+..........#+........:@@:              @@-    %*                   
            ##====================*@@@             #@-      @#                  
           -@-        .           =@%             +@=       -@%.                
          -@@.       *@@-         @#             +@=         -@@=               
         -@@#        @@:         -*             *@-           -@@%:             
         -@*        =@#          .             *%.             .@@@#            
                    %@:                       ##               : *@@@*.         
                   :@%             @*        #-               +@* -@@@%         
          ---------%@#------------#@@#     :#  %%%%%%%%%%%%%%%@@@#  #%          
          --------*@%-------=@@*------    +-           @@                       
                  *@=       :@@          .             @@                       
                  @%        +@*                        @@                       
                 *@-        @@.                        @@                       
                .@%        =@#                         @@       :               
                #@:        @@:                         @@      =@#              
               :@#        *@*                 -########@@%#####@@@#             
               =@#-      :@@                           @@.                      
                  =%@#=.:@@:                           @@                       
                    .+%@@@%                            @@                       
                      =@@@@@#:                         @@                       
                     *@%  -%@@@+                       @@                       
                   +@%-     :#@@@+                     @@          +            
                :*@#:         :#@@@.                   @@.        =@@:          
             -*%+-              -%@@      -############%%#########%%%%          
         .+*+-                    #@.                                           
'''

# ------------------------------------------------------------------------------------ #
# 敏感命令二次確認機制
# 用途: 對於危險操作（刪除模型、pip install、shell exec）採用確認碼機制，
#       防止誤觸。使用者發送確認碼後才真正執行。
# 全域變數:
#   pending_confirmations : 儲存待確認的命令，key=token, value={cmd, args, chat_id, timestamp}
# ------------------------------------------------------------------------------------ #
pending_confirmations = {}
def generate_token(chat_id: str, cmd: str, args: str) -> str:
    """生成一次性確認 token"""
    raw = f"{chat_id}_{cmd}_{args}_{time.time()}_{os.urandom(4).hex()}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]

def confirm_command(chat_id: str, token: str) -> tuple:
    """嘗試確認命令，返回 (成功標誌, 結果字串)"""
    if token not in pending_confirmations:
        return False, "❌ 確認碼無效或已過期。請重新發送原命令。"
    info = pending_confirmations[token]
    if str(info["chat_id"]) != str(chat_id):
        return False, "❌ 確認碼與用戶不匹配。"
    # 檢查是否超時（30秒）
    if time.time() - info["timestamp"] > 30:
        del pending_confirmations[token]
        return False, "❌ 確認碼已超時（30秒）。請重新發送原命令。"
    # 執行實際命令
    cmd_type = info["cmd"]
    args = info["args"]
    del pending_confirmations[token]  # 用完即刪
    if cmd_type == "ollama_rm":
        success, result = execute_ollama_rm(args)
    elif cmd_type == "pip_install":
        success, result = execute_pip_install(args)
    elif cmd_type == "shell_exec":
        success, result = execute_shell_command(args)
    else:
        return False, "❌ 未知命令類型。"
    return success, result


# 從環境變量獲取管理員 ID，用於敏感操作權限檢查

ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID", "")
'''
def is_admin(chat_id: str) -> bool:
    """判斷當前用戶是否為管理員"""
    return str(chat_id) == ADMIN_CHAT_ID
'''
def is_admin(chat_id: str) -> bool:
    # 網頁版自動放行
    if chat_id and not chat_id.isdigit():
        return True
    return str(chat_id) == ADMIN_CHAT_ID











'''
                                                               -.                 -:                
                                                              -@*                 @#.               
             -=+=:    ...          ...   ......               @- +               ## +               
           =#:   :%   .#@.        +@=.   .#@:..-#+           %-  .#             =%   #              
          *#      %.   =%*        %@.     +@     =%.        #:    .%=          -%    :%.            
         =@       +.   -=@       --@.     +@      +%      :+      = *@+       -*      :@+           
         @+            - @+      + @.     +@       @=    =: =====+*- .%@=    ==   +=    %@+         
        :@:            - +@     ::.@.     +@       ##  .:              :    =.     @.    *@#        
        +@             = .@:    + .@.     +@       *%         :  .    :    -       =      :         
        +@             =  ##    = .@.     +@       +@    *+::+@  @===*%                 =           
        +@             =  -@   =  .@.     +@       +@    *.  .#  %   :*      ----------%@-          
        -@.            =   %+  +  .@.     +@       ##    *.  .#  %   :*               :%.           
         @=            =   =@ :.  .@.     +@       @=    *.  .#  %   :*              .#             
         *%       --   =    @-+   .@.     +@      =@     *.  .#  %   :*         .    *              
          @=      +-   =    *@-   .@.     +@     .@-     *+--+#  %   :*          *=.=               
           %=     %-   +    :@    .@.     +@    =#:      *.  .#  %  -@=           +@.               
            =*+==+:  .=*+=   -   =+*+=   =+*====.        =       %   :             +@:              
                                                                 #                  =#              
'''



# ------------------------------------------------------------------------------------ #
# 函數: is_model_running
# 用途: 檢查指定模型是否正在被 Ollama 使用（已載入記憶體）。
# 設計:
#   執行 ollama ps 取得當前運行中的模型列表，比對模型名稱。
#   若發生異常（如 ollama 未運行），返回 False 並記錄日誌。
# 參數:
#   model_name: 要檢查的模型名稱。
# 返回:
#   bool: True 表示正在運行，False 表示未運行或檢查失敗。
# ------------------------------------------------------------------------------------ #
def is_model_running(model_name: str) -> bool:
    """檢查模型是否正在被 Ollama 使用"""
    try:
        result = subprocess.run(
            "ollama ps", shell=True, capture_output=True, text=True, timeout=10
        )
        # 提取運行的模型名稱（格式：NAME      ID    SIZE    PROCESSOR    UNTIL）
        lines = result.stdout.strip().split('\n')[1:]  # 跳過表頭
        for line in lines:
            parts = line.split()
            if parts and parts[0] == model_name:
                return True
        return False
    except Exception:
        return False  # 如果檢查出錯，為安全起見默認認為不在運行，但可以記錄日誌


# ------------------------------------------------------------------------------------ #
# 函數: show_current_model
# 用途: 顯示當前 agent 正在使用的模型名稱（從配置檔讀取）。
# 設計:
#   透過 get_config_file_path 讀取設定檔，提取 MOK_MODEL_NAME 的值。
#   若配置檔不存在或無該變數，返回默認提示。
# 返回:
#   str: 模型名稱訊息。
# ------------------------------------------------------------------------------------ #
def show_current_model() -> str:
    """顯示當前正在使用的模型名稱（直接從配置文件讀取）"""
    config_path = get_config_file_path()
    if not config_path:
        return "❌ 無法定位配置文件"
    try:
        with open(config_path, "r") as f:
            for line in f:
                if line.startswith("MOK_MODEL_NAME="):
                    current_model = line.split("=", 1)[1].strip()
                    return f"🤖 當前使用的模型：{current_model}"
        return "🤖 當前使用的模型：未設置（將使用默認值 qwen3:1.7b）"
    except Exception as e:
        return f"❌ 讀取配置失敗: {e}"




# ------------------ 模型切換相關函數 ------------------
# ------------------------------------------------------------------------------------ #
# 函數: set_model_in_config
# 用途: 修改配置檔中的 MOK_MODEL_NAME，並排程重啟 Agent。
# 設計:
#   讀取原配置檔，更新或新增 MOK_MODEL_NAME 行，寫回檔案。
#   使用 subprocess.Popen 在 2 秒後執行 pm2 restart，使新模型生效。
# 參數:
#   new_model: 新的模型名稱。
# 返回:
#   str: 操作結果訊息。
# ------------------------------------------------------------------------------------ #
def set_model_in_config(new_model: str) -> str:
    """修改配置文件中的 MOK_MODEL_NAME，返回結果說明"""
    config_path = get_config_file_path()
    if not config_path:
        return "❌ 無法定位配置文件。"
    try:
        with open(config_path, "r") as f:
            lines = f.readlines()
        new_lines = []
        found = False
        for line in lines:
            if line.startswith("MOK_MODEL_NAME="):
                new_lines.append(f"MOK_MODEL_NAME={new_model}\n")
                found = True
            else:
                new_lines.append(line)
        if not found:
            new_lines.append(f"MOK_MODEL_NAME={new_model}\n")
        with open(config_path, "w") as f:
            f.writelines(new_lines)

        subprocess.Popen(
            f"(sleep 2 && pm2 restart {mokagi_name}_{agent_name}) &",
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return f"✅ 已將模型設置為 `{new_model}`。\n將在2秒後自動重啟 Agent 使修改生效。"

    except Exception as e:
        return f"❌ 寫入配置文件失敗: {e}"




# ==============================================
# ==============================================
# ================= 危險命令 ====================
# ==============================================
# ==============================================
# ------------------------------------------------------------------------------------ #
# 函數: execute_ollama_rm
# 用途: 實際執行 ollama rm 刪除模型。
# 設計:
#   使用 subprocess 執行 shell 命令，捕獲輸出。
#   此函數僅在二次確認後被呼叫。
# 參數:
#   model_name: 要刪除的模型名稱。
# 返回:
#   tuple (成功標誌, 結果訊息)
# ------------------------------------------------------------------------------------ #
def execute_ollama_rm(model_name: str) -> tuple:
    """實際執行刪除模型"""
    try:
        result = subprocess.run(
            f"ollama rm {model_name}", shell=True, capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            return True, f"✅ 模型 {model_name} 已刪除。"
        else:
            return False, f"❌ 刪除失敗: {result.stderr}"
    except Exception as e:
        return False, f"❌ 執行失敗: {e}"


# ------------------------------------------------------------------------------------ #
# 函數: execute_pip_install
# 用途: 實際執行 pip install 安裝 Python 套件。
# 設計:
#   自動添加 --user 參數避免權限問題，超時時間 300 秒。
#   輸出結果截取最後 3000 字符防止訊息過長。
# 參數:
#   rest: 套件名稱或其他 pip 參數。
# 返回:
#   tuple (成功標誌, 結果訊息)
# ------------------------------------------------------------------------------------ #
def execute_pip_install(rest: str) -> tuple:
    """實際執行 pip install"""
    if "--user" not in rest:
        rest = "--user " + rest
    cmd = f"pip install {rest}"
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            output = html.escape(result.stdout[-3000:]) if result.stdout else "安裝成功，無控制檯輸出。"
            return True, f"✅ pip 安裝成功\n<pre>{output}</pre>"
        else:
            error = html.escape(result.stderr[-3000:]) if result.stderr else "未知錯誤。"
            return False, f"❌ pip 安裝失敗\n<pre>{error}</pre>"
    except subprocess.TimeoutExpired:
        return False, "❌ 安裝超時（超過300秒）。"
    except Exception as e:
        return False, f"❌ 執行失敗: {html.escape(str(e))}"




# ------------------------------------------------------------------------------------ #
# 函數: execute_shell_command
# 用途: 實際執行任意 Shell 命令（需二次確認）。
# 設計:
#   使用 /bin/bash 執行，超時 300 秒。成功時返回 stdout，失敗時返回 stderr。
#   輸出截取最後 3000 字符。
# 參數:
#   command: 要執行的 Shell 命令字串。
# 返回:
#   tuple (成功標誌, 結果訊息)
# ------------------------------------------------------------------------------------ #
def execute_shell_command(command: str) -> tuple[bool, str]:
    """執行任意 Shell 命令，返回 (成功標誌, 結果信息)"""
    try:
        result = subprocess.run(
            command, shell=True,
            capture_output=True, text=True,
            timeout=300,          # 最長等待 5 分鐘
            executable="/bin/bash"
        )
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        if result.returncode == 0:
            output = stdout if stdout else "命令執行成功（無輸出）"
            # 截取最後 3000 字符防止消息過長
            return True, f"✅ 命令執行成功\n<pre>{html.escape(output[-3000:])}</pre>"
        else:
            err_msg = stderr if stderr else stdout
            return False, f"❌ 命令執行失敗 (返回碼 {result.returncode})\n<pre>{html.escape(err_msg[-3000:])}</pre>"
    except subprocess.TimeoutExpired:
        return False, "❌ 命令執行超時（超過 300 秒）"
    except Exception as e:
        return False, f"❌ 執行異常: {html.escape(str(e))}"































































# ================= 自然化函數 =================

# ------------------------------------------------------------------------------------ #
# 函數: naturalize_admin_result
# 用途: 將 admin 工具返回的 JSON 結果轉換為自然口語的回覆。
# 設計:
#   根據 action 欄位分別構建結構化句子，然後讓 LLM 用更自然的口吻重新表達。
#   支援流式輸出（透過 temp_msg 和 context 參數，本函數目前僅做一次性轉換）。
#   若 LLM 呼叫失敗則返回結構化備用句子。
# 參數:
#   user_text: 原始使用者輸入。
#   raw_result: admin 工具返回的 JSON 字串。
#   ollama_api, model_name: Ollama 設定。
#   temp_msg, context: 用於流式更新（目前未使用，保留接口）。
# 返回:
#   str: 自然語言結果。
# ------------------------------------------------------------------------------------ #
async def naturalize_admin_result(user_text: str, raw_result: str, ollama_api: str, model_name: str, temp_msg=None, context=None) -> str:
    """
    將 admin 工具的 JSON 結果口語化。
    """
    try:
        data = json.loads(raw_result)
    except:
        return raw_result   # 非 JSON 直接原始返回

    action = data.get("action", "")
    # 根據不同 action 構建給 LLM 的提示
    structured = ""
    if action == "show_models":
        current = data.get("current_model", "")
        models = data.get("models", [])
        models_str = "、".join(models) if models else "無"
        structured = f"當前使用的模型是 {current}。主機上已安裝的模型有：{models_str}。"

    elif action == "set_model":
        model = data.get("model", "")
        structured = f"已成功將運行模型切換為 {model}，兩秒後自動重啟生效。"

    elif action == "ollama_rm":
        model = data.get("model", "")
        structured = f"已成功刪除模型 {model}。"

    elif action == "pip_install":
        package = data.get("package", "")
        output_summary = data.get("output", "")[:200]
        structured = f"已成功安裝 Python 套件 {package}。安裝摘要：{output_summary}"

    elif action == "shell_exec":
        command = data.get("command", "")
        output_summary = data.get("output", "")[:200]
        structured = f"Shell 命令執行成功。命令：{command}。輸出摘要：{output_summary}"

    elif action == "system_monitor":
        monitor_type = data.get("type", "")
        output = data.get("output", "")
        if monitor_type == "htop":
            structured = f"當前系統負載信息如下：\n{output[:500]}"
        elif monitor_type == "cpu":
            structured = f"當前 {output}"
        elif monitor_type == "logs":
            lines = data.get("lines", "")
            structured = f"最近的 {lines} 行日誌如下：\n\n{output[:1500]}"
        else:
            structured = f"系統信息：{output[:500]}"

    elif action == "read_file":
        path = data.get("path", "")
        lines = data.get("lines", "")
        content = data.get("content", "")
        if lines == "all":
            line_desc = "全文"
        else:
            line_desc = f"前 {lines} 行"
        preview = content[:500] + ("..." if len(content) > 500 else "")
        structured = f"已讀取文件 {path} 的 {line_desc}，內容如下：\n{preview}"

    else:
        return raw_result   # 無法識別的 action 直接返回原始 JSON

    # 讓 LLM 用更自然的語氣說一遍
    prompt = f"""你是一個管理助手。以下是系統操作結果：
{structured}

請用自然的口語，像跟同事報告一樣，告訴使用者這項操作的結果。可以直接說，不需要開場白。"""

    try:
        payload = {
            "model": model_name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": 2000,
                "temperature": 0.5,
                "top_p": 0.9,
            }
        }
        async with httpx.AsyncClient(timeout=180) as client:
            resp = await client.post(ollama_api, json=payload)
            if resp.status_code == 200:
                data_resp = resp.json()
                reply = data_resp.get("response", "").strip()
                if reply:
                    return reply
    except Exception as e:
        logging.warning(f"管理結果自然化 LLM 調用失敗: {e}")

    # 備用：直接返回結構化語句
    return structured






'''
                           .                                                    
                @%+        @@=                                                  
               =@%         @%                =*.                 :@*            
               %@=         @%      ::        =@%*******@@%*******#@@#           
              .@@          @%      @@=       =@=       *@:        @#            
              =@* #%%%%%%%%@@%%%%%@@@@-      =@=       *@:        @*            
              %@           @%                =@=       *@:        @*            
             .@#           @%                =@=       *@:        @*            
             *@.           @%      :         =@=       *@:        @*            
             @@+   %*:::::=@@:::::*@*        =@=       *@:        @*            
            +@@:   %@=----=@@-----*@@:       =@#=======%@*=======+@*            
            @@@.   %@      @%     -@=        =@*::::::.#@+:::::::=@*            
           +#%@.   %@      @%     -@=        =@=       *@:        @*            
           @.*@.   %@      @%     -@=        =@=       *@:        @*            
          *- *@.   %@      @%     -@=        =@=       *@:        @*            
         .*  *@.   %@      @#     -@=        +@-       *@:        @*            
         =   *@.   %@+----+@%-----*@=        +@:       *@:        @*            
             *@.   %@-::::+@#:::::*@=        *@:       *@:        @*            
             *@.   %#     :@=     :%.        #@%#######@@%#######%@*            
             *@.     .    =@:                %@        #@=       :@*            
             *@.     +    #@                 @#        *@:        @*            
             *@.     .*   @#                 @+        *@:        @*            
             *@.      +# =@:                :@:        *@:        @*            
             *@.       ##@#                 +@         *@:        @*            
             *@.        @@+                 %*         *@:        @*            
             *@.       #@#@%-              .@          *@:        @*            
             *@.      ##  -@@@*-           *+          *@:        @*            
             *@.    -%-     +@@@@@*+-:.    %           *@:   -=+=*@*            
             *@.  -#=         -#@@@@@%    *.           *@:     :@@@-            
             *% =*-              :+%@.   ::            +*       #%=             
'''

# ------------------------------------------------------------------------------------ #
# 函數: handle_admin
# 用途: 管理命令的總入口，根據 args 路由到不同操作。
# 設計:
#   1. 無參數時顯示幫助訊息。
#   2. 處理確認命令 (/admin confirm token)。
#   3. 公開命令（htop, cpu, mode, logs, read_file）直接執行。
#   4. 敏感命令（set_model, ollama_rm, pip, exec）需檢查管理員權限及二次確認。
# 參數:
#   args: 命令參數字串。
#   chat_id: 使用者 Telegram ID（用於權限檢查）。
# 返回:
#   str: 執行結果，多為 JSON 字串或普通訊息。
# ------------------------------------------------------------------------------------ #
async def handle_admin(args: str, chat_id: str = None) -> str:
    """
    管理命令路由，根據 args 執行不同操作
    用法示例：
        /admin htop
        /admin mode
        /admin ollama_rm mok_3b:latest
    """
    logging.info(f"Admin plugin invoked: args='{args}', chat_id={chat_id}")
    args = args.strip()
    if not args:
        help_text = f'''
{PLUGIN_INFO["icon"]} 管理命令說明：


    讀取檔案內容 [檔案路徑] [行數]<pre>/admin read_file 檔案路徑 行數</pre>

    查看系統負載<pre>/admin htop</pre>

    查看 CPU 使用率<pre>/admin cpu</pre>

    查看已安裝的模型<pre>/admin mode</pre>

    查看 {mokagi_name}_{agent_name} 日誌 (預設15行)<pre>/admin logs 行數</pre>

    切換模型<pre>/admin set_model 模型名</pre>

    刪除指定模型<pre>/admin ollama_rm 模型名</pre>

    安裝 Python 套件<pre>/admin pip install 包名</pre>

    Shell 命令執行<pre>/admin exec Shell 命令</pre>

=====
🧩 自然語言意圖辨識：
'''
        # 動態添加 intent_keywords（不轉義）
        for keyword, cmd in PLUGIN_INFO["intent_keywords"]:
            help_text += f'   "{keyword}" → {cmd}\n'
        return help_text


    if args.startswith("confirm "):
        # 確認命令
        token = args.split(maxsplit=1)[1].strip()
        success, result = confirm_command(chat_id, token)
        return result




# ==============================================
# ==============================================
# ======= 公開命令：任何授權用戶都可執行 ==========
# ==============================================
# ==============================================

    # -------------------------------------------------------------------------------- #
    # 命令: htop
    # 用途: 顯示系統負載摘要（top 前 5 行）。
    # 返回: JSON 格式 {action:"system_monitor", type:"htop", output:...}
    # -------------------------------------------------------------------------------- #
    if args == "htop":
        # 顯示系統負載
        try:
            result = subprocess.run(
                "top -bn1 | head -n 5", shell=True, capture_output=True, text=True, timeout=10
            )
            if result.stdout:
                return json.dumps({
                    "action": "system_monitor",
                    "type": "htop",
                    "output": result.stdout.strip()
                }, ensure_ascii=False)
            else:
                return f"<pre>{result.stdout}</pre>" if result.stdout else "無法獲取系統負載。"
        except Exception as e:
            return f"❌ 執行失敗: <pre>{e}</pre>"

    # -------------------------------------------------------------------------------- #
    # 命令: cpu
    # 用途: 計算並顯示當前 CPU 使用率（從 /proc/stat 讀取）。
    # 返回: JSON 格式 {action:"system_monitor", type:"cpu", output:...}
    # -------------------------------------------------------------------------------- #
    elif args == "cpu":
        # 顯示 CPU 使用率
        try:
            result = subprocess.run(
                "grep 'cpu ' /proc/stat | awk '{print \"CPU使用率: \" ($2+$4)*100/($2+$4+$5) \"%\"}'",
                shell=True, capture_output=True, text=True, timeout=10
            )
            if result.stdout:
                return json.dumps({
                    "action": "system_monitor",
                    "type": "cpu",
                    "output": result.stdout.strip()
                }, ensure_ascii=False)
            else:
                return "無法獲取 CPU 使用率。"
        except Exception as e:
            return f"❌ 執行失敗: <pre>{e}</pre>"

    # -------------------------------------------------------------------------------- #
    # 命令: mode
    # 用途: 顯示當前使用的模型以及 Ollama 中已安裝的所有模型列表。
    # 返回: JSON 格式 {action:"show_models", current_model:..., models:[...]}
    # -------------------------------------------------------------------------------- #
    elif args == "mode":
        # 顯示已安裝的模型
        try:
            now_model = show_current_model()
            # 提取純模型名
            if "：" in now_model:
                now_model = now_model.split("：", 1)[1]
            result = subprocess.run(
                "ollama list", shell=True, capture_output=True, text=True, timeout=30
            )
            if result.stdout:
                models = [line.split()[0] for line in result.stdout.strip().split('\n')[1:] if line.split()]
            else:
                models = []
            return json.dumps({
                "action": "show_models",
                "current_model": now_model,
                "models": models
            }, ensure_ascii=False)
        except Exception as e:
            return f"❌ 執行失敗: <pre>{e}</pre>"

    # -------------------------------------------------------------------------------- #
    # 命令: logs [行數]
    # 用途: 顯示當前 agent 的 pm2 日誌，預設 15 行，可指定行數。
    # 返回: JSON 格式 {action:"system_monitor", type:"logs", lines:..., output:...}
    # -------------------------------------------------------------------------------- #
    elif args.startswith("logs"):
        # 顯示日誌
        num = args[5:].strip()
        if not num:
            num = 15
        try:
            result = subprocess.run(
                f"pm2 logs {mokagi_name}_{agent_name} --lines {num} --nostream --raw",
                shell=True, capture_output=True, text=True, timeout=30
            )
            if result.stdout:
                return json.dumps({
                    "action": "system_monitor",
                    "type": "logs",
                    "lines": num,
                    "output": result.stdout.strip()[-4000:]
                }, ensure_ascii=False)
            else:
                return "沒有日誌。"
        except Exception as e:
            return f"❌ 執行失敗: <pre>{e}</pre>"

    # -------------------------------------------------------------------------------- #
    # 命令: read_file <檔案路徑> [行數]
    # 用途: 讀取指定檔案的前 N 行（N 預設為 None 表示讀取全文）。
    # 設計:
    #   使用 cat 或 head 命令，並限制輸出長度避免超過 Telegram 訊息上限。
    #   路徑安全限制已被註解，可視需求開啟。
    # 返回: JSON 格式 {action:"read_file", path:..., lines:..., content:...}
    # -------------------------------------------------------------------------------- #
    elif args.startswith("read_file"):
        # /admin read_file <filepath> [lines]
        parts = args.split()
        if len(parts) < 2:
            return "用法: /admin read_file [檔案路徑] [行數]\n例：/admin read_file intent.py 20  (讀取前20行)\n若不指定行數，則讀取整個檔案。"
        filepath = parts[1]
        lines = parts[2] if len(parts) > 2 else None
        # 安全限制：只允許讀取當前專案目錄內的文件（可自定義）
        #allowed_root = os.path.expanduser(f"~/.{mokagi_name}")
        real_path = os.path.realpath(filepath)
        #if not real_path.startswith(allowed_root):
        #    return "⛔ 只允許讀取專案目錄內的檔案。"
        try:
            if lines is None:
                # 讀取全文
                cmd = f"cat '{real_path}'"
                line_info = "全文"
            else:
                # 讀取前 lines 行
                cmd = f"head -{lines} '{real_path}'"
                line_info = f"前 {lines} 行"
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=180   # 全文讀取可能耗時稍長
            )
            if result.returncode == 0:
                output = result.stdout
                if not output:
                    output = "(檔案為空)"
                # 限制輸出長度，避免超過 Telegram 消息上限（約 4000 字符）
                MAX_LEN = 3500
                if len(output) > MAX_LEN:
                    output = output[:MAX_LEN] + "\n\n... (內容過長，已截斷)"
                return json.dumps({
                    "action": "read_file",
                    "path": filepath,
                    "lines": lines if lines is not None else "all",
                    "content": output
                }, ensure_ascii=False)
            else:
                return f"❌ 讀取失敗: {result.stderr}"
        except subprocess.TimeoutExpired:
            return "❌ 讀取超時，檔案可能過大。"
        except Exception as e:
            return f"❌ 執行失敗: {e}"

# ==============================================
# ==============================================
# =========== 敏感命令：需要二次確認 =============
# ==============================================
# ==============================================

    if not chat_id or not is_admin(chat_id):
        return "⛔ 此操作僅限管理員執行。"

    # -------------------------------------------------------------------------------- #
    # 命令: set_model <模型名>
    # 用途: 切換當前 agent 使用的 Ollama 模型，會自動重啟 Agent。
    # 注意: 屬於管理員操作，直接執行（無二次確認），但會重啟進程。
    # 返回: 設定結果訊息。
    # -------------------------------------------------------------------------------- #
    if args.startswith("set_model"):
        new_model = args[10:].strip()
        if not new_model:
            return "用法: /admin set_model <模型名稱>\n例：/admin set_model llama3.2:3b"
        return set_model_in_config(new_model)


    # -------------------------------------------------------------------------------- #
    # 命令: ollama_rm <模型名>
    # 用途: 從 Ollama 刪除指定模型。需要二次確認且模型不能正在運行。
    # 返回: 確認碼訊息或錯誤。
    # -------------------------------------------------------------------------------- #
    if args.startswith("ollama_rm"):
        parts = args.split()
        if len(parts) < 2:
            return "用法: /admin ollama_rm 模型名稱"
        model_name = parts[1]
        if is_model_running(model_name):
            return f"⛔ 錯誤：模型 {model_name} 正在使用中，無法刪除。請先停止使用該模型的應用。"
        token = generate_token(chat_id, "ollama_rm", model_name)
        pending_confirmations[token] = {
            "cmd": "ollama_rm",
            "args": model_name,
            "chat_id": chat_id,
            "timestamp": time.time()
        }
        return f"⚠️ 危險操作 ⚠️\n[刪除模型：`{model_name}]`\n請在30秒內發送以下命令以確認：\n<pre>/admin confirm {token}</pre>"



    # -------------------------------------------------------------------------------- #
    # 命令: pip install <包名>
    # 用途: 安裝 Python 套件，需要二次確認。
    # 返回: 確認碼訊息或錯誤。
    # -------------------------------------------------------------------------------- #
    if args.startswith("pip"):
        rest = args[len("pip"):].strip()
        if rest.startswith("install"):
            rest = rest[len("install"):].strip()
        if not rest:
            return "用法: /admin pip install <包名>\n例：/admin pip install requests"
        # 生成確認碼
        token = generate_token(chat_id, "pip_install", rest)
        pending_confirmations[token] = {
            "cmd": "pip_install",
            "args": rest,
            "chat_id": chat_id,
            "timestamp": time.time()
        }
        return f"⚠️ 危險操作 ⚠️\n[pip 安裝：`{rest}`]\n請在30秒內回覆確認碼：\n<pre>/admin confirm {token}</pre>"






    # -------------------------------------------------------------------------------- #
    # 命令: exec <Shell 命令>
    # 用途: 執行任意 Shell 命令，需要二次確認。
    # 返回: 確認碼訊息或錯誤。
    # -------------------------------------------------------------------------------- #
    if args.startswith("exec"):
        rest = args[len("exec"):].strip()
        if not rest:
            return "用法: /admin exec <Shell 命令>\n例如：/admin exec curl -fsSL https://get.docker.com | sh"
        token = generate_token(chat_id, "shell_exec", rest)
        pending_confirmations[token] = {
            "cmd": "shell_exec",
            "args": rest,
            "chat_id": chat_id,
            "timestamp": time.time()
        }
        return (
            f"⚠️ 危險操作 ⚠️\n[執行命令：`{html.escape(rest)}`]\n\n請在30秒內發送確認碼以執行：\n<pre>/admin confirm {token}</pre>"
        )


    return f"未知管理命令: {args}\n發送 /admin 查看可用命令。"