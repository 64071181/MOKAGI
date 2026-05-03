PLUGIN_INFO = {
    "command": "/admin",  # 這個命令會出現在 TG 菜單
    "icon":"🤖",
    "handler": "handle_admin",
    "description": "管理工具 (htop, ollama list, rm, pip install 等)",
    "intent_keywords": [
        ("htop", "/admin htop"),

        ("cpu", "/admin cpu"),

        ("模型列表", "/admin mode"),

        ("切換模型", "/admin set_model "),

        ("日誌", "/admin logs")
    ],
    "updata":"202605040059"
}

import os
import subprocess
import logging
import html
import time
import hashlib


mokagi_name = os.environ.get("AD_AgiName")
agent_name = os.environ.get("AD_AGENT_NAME")





# ------------------ 輔助函數：獲取當前 agent 的配置文件路徑 ------------------
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

# 敏感命令 二次確認機制
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
    else:
        return False, "❌ 未知命令類型。"
    return success, result



# 敏感命令實際執行
def execute_ollama_rm(model_name: str) -> tuple:
    """實際執行刪除模型"""
    try:
        result = subprocess.run(
            f"ollama rm {model_name}", shell=True,
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            return True, f"✅ 模型 {model_name} 已刪除。"
        else:
            return False, f"❌ 刪除失敗: {result.stderr}"
    except Exception as e:
        return False, f"❌ 執行失敗: {e}"

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

# 從環境變量獲取管理員 ID，用於敏感操作權限檢查
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID", "")

def is_admin(chat_id: str) -> bool:
    """判斷當前用戶是否為管理員"""
    return str(chat_id) == ADMIN_CHAT_ID

def is_model_running(model_name: str) -> bool:
    """檢查模型是否正在被 Ollama 使用"""
    try:
        result = subprocess.run(
            "ollama ps", shell=True,
            capture_output=True, text=True, timeout=10
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
def handle_admin(args: str, chat_id: str = None) -> str:
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
🤖 管理命令：

    查看系統負載<pre>/admin htop</pre>

    查看 CPU 使用率<pre>/admin cpu</pre>

    查看已安裝的模型<pre>/admin mode</pre>

    切換模型<pre>/admin set_model 模型名</pre>

    刪除指定模型<pre>/admin ollama_rm 模型名</pre>

    查看 {mokagi_name}_{agent_name} 日誌 (預設15行)<pre>/admin logs 行數</pre>

    安裝 Python 套件<pre>/admin pip install 包名</pre>

=====
🧩 自然語言意圖辨識：
        '''
        # 動態添加 intent_keywords（不轉義）
        for keyword, cmd in PLUGIN_INFO["intent_keywords"]:
            help_text += f'   "{keyword}" → {cmd}\n'
        return help_text


    # --- 確認命令 ---
    if args.startswith("confirm "):
        token = args.split(maxsplit=1)[1].strip()
        success, result = confirm_command(chat_id, token)
        return result




    # --- 模型切換命令（僅管理員）---
    if args.startswith("set_model"):
        if not chat_id or not is_admin(chat_id):
            return "⛔ 此操作僅限管理員執行。"
        new_model = args[10:].strip()
        if not new_model:
            return "用法: /admin set_model <模型名稱>\n例：/admin set_model llama3.2:3b"
        return set_model_in_config(new_model)





    # --- 公開命令（任何授權用戶都可執行）---
    if args == "htop":
        try:
            result = subprocess.run(
                "top -bn1 | head -n 5", shell=True,
                capture_output=True, text=True, timeout=10
            )
            return f"<pre>{result.stdout}</pre>" if result.stdout else "無法獲取系統負載。"
        except Exception as e:
            return f"❌ 執行失敗: {e}"

    elif args == "cpu":
        try:
            result = subprocess.run(
                "grep 'cpu ' /proc/stat | awk '{print \"CPU使用率: \" ($2+$4)*100/($2+$4+$5) \"%\"}'",
                shell=True, capture_output=True, text=True, timeout=10
            )
            return f"🖥 {result.stdout.strip()}"
        except Exception as e:
            return f"❌ 執行失敗: {e}"




    elif args == "mode":
        try:
            nowModel = show_current_model()
            result = subprocess.run(
                "ollama list", shell=True,
                capture_output=True, text=True, timeout=30
            )
            return f"{nowModel}\n\n <pre>{result.stdout}</pre>" if result.stdout else "沒有安裝任何模型。"
        except Exception as e:
            return f"❌ 執行失敗: {e}"











    elif args.startswith("logs"):
        # 默認顯示 15 行，可指定 /admin logs 30
        lines = args.split()
        num = lines[1] if len(lines) > 1 and lines[1].isdigit() else 15
        try:
            result = subprocess.run(
                f"pm2 logs {mokagi_name}_{agent_name} --lines {num} --nostream --raw", shell=True,
                capture_output=True, text=True, timeout=30
            )
            return f"<pre>{result.stdout[-4000:]}</pre>" if result.stdout else "沒有日誌。"
        except Exception as e:
            return f"❌ 執行失敗: {e}"

















# ==============================================
# ==============================================
# =========== 敏感命令：需要二次確認 =============
# ==============================================
# ==============================================

    if not chat_id or not is_admin(chat_id):
        return "⛔ 此操作僅限管理員執行。"

    # 處理 pip install
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

    # 處理 ollama_rm
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

    return f"未知管理命令: {args}\n發送 /admin 查看可用命令。"



















# ------------------ 模型切換相關函數 ------------------
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



