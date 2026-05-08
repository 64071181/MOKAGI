

#!/usr/bin/env bash
# "start":"202604231241"
# "updata":"202505081143"
# ==============================================
# ==============================================
# ================== 基礎設定 ===================
# ==============================================
# ==============================================

# 先刪除舊的資料夾(如果有的話）
# rm -rf ~/.MokAgi


set -o pipefail # 讓管道中任何一個命令失敗都會導致整個指令碼失敗
MokAgiName="MokAgi" # 專案名稱，影響資料夾和日誌命名
PROJECT_DIR="${HOME}/.${MokAgiName}"   # 專案根目錄，存放機器人指令碼和 .env 等檔案
BOT_SCRIPT="${PROJECT_DIR}/${MokAgiName}.py" # 機器人執行主指令碼

# ================== 一切 token ===================
ENV_FILE="${PROJECT_DIR}/.env"



# ================== MokAgi Github 工具庫 ===================
GITHUB_TOOLS_REPO="https://github.com/64071181/MokAgi/tree/main/tools"
githubToolsUrl="https://raw.githubusercontent.com/64071181/MokAgi/refs/heads/main/tools"
# ================== cmd提示 顏色定義 ===================
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

















echo -e "${GREEN}=========================================="
echo -e " [1/8] 環境設定 "
echo -e "==========================================${NC}"

# ================== 建立專案根目錄 ===================
mkdir -p "${PROJECT_DIR}"
toolsUrl="${PROJECT_DIR}/tools"
mkdir -p "${toolsUrl}"

cd "${PROJECT_DIR}"

# ================== 檢查並準備環境配置檔案 ===================
# 列出所有符合的設定檔（以點開頭，但不是 .env 也不是 .. 或 .）
shopt -s dotglob
configs=( "${PROJECT_DIR}"/.[!.]* )
shopt -u dotglob
valid_configs=()
for cfg in "${configs[@]}"; do
    [[ -f "$cfg" && "$(basename "$cfg")" != ".env" ]] && valid_configs+=("$cfg")
done

if [ ${#valid_configs[@]} -eq 0 ]; then
    # 沒有任何現有設定檔 → 請使用者輸入新 agent 名稱
    echo -e "${YELLOW}請輸入此 Agent 的名稱（例如：溟、沐、sam）:${NC}"
    read -p "Agent 名稱: " AGENT_NAME_INPUT
    AGENT_NAME_INPUT=$(echo "$AGENT_NAME_INPUT" | xargs | cut -c1-32)
    if [ -z "$AGENT_NAME_INPUT" ]; then
        AGENT_NAME_INPUT="default"
    fi
    # 配置檔名稱改為 .<agent名稱>
    ENV_FILE="${PROJECT_DIR}/.${AGENT_NAME_INPUT}"
    echo -e "${GREEN}將建立配置檔案：${ENV_FILE}${NC}"
    
    # 生成配置檔案，其中 AGENT_NAME 設為使用者輸入的名稱
    cat > "${ENV_FILE}" << 'ENV_TEMPLATE'
# ${MokAgiName} 環境變數配置（請填寫你的資訊）
# 注意：等號前後不要加空格 " '

# agent名稱
AGENT_NAME=__AGENT_NAME_PLACEHOLDER__

# Telegram Bot Token
TG_TOKEN=你的Bot_Token

# 管理員 Chat ID（部署成功後會收到通知）
ADMIN_CHAT_ID=你的Telegram_Chat_ID

# 允許使用機器人的使用者 ID，多個用英文逗號分隔 (留空則所有人可用)
ALLOWED_USERS=你的ID,受權使用者ID1,受權使用者ID2（逗號分隔，留空則所有人可用）

# ================== 模型設定 ===================
MOK_MODEL_NAME=qwen3:1.7b
# 這裡指定 Ollama 模型名稱，可在 https://ollama.com/ 直接找其他模型

MOK_MODEL_api=http://localhost:11434/api/generate
# Ollama API 端點，保持不變

MOK_MAX_HISTORY_ROUNDS=6
# 對話歷史保留輪數，過多會增加上下文長度，過少則無記憶感

MOK_num_ctx=16384
# 模型的上下文視窗大小(如 8192、16384）(32768 = 約 2.2 萬個中文字 / 40 到 50 頁 A4 紙滿滿的文字量）

MOK_num_predict=8192
# 模型的最大生成長度(如 2048、4096、8192）(8192 = 5,400 中文字 / 6 頁 A4 紙滿滿的文字量)

MOK_temperature=0.8
# 溫度 / 隨機性(0 嚴謹, 1.0+ 創意)

MOK_repeat_penalty=1.5
# 重複懲罰，防止鬼打牆(1.0:不懲罰，2.0:太高)

MOK_presence_penalty=0.6
# 字重複施加懲罰。正值增加新詞可能性，負值鼓勵重複

MOK_frequency_penalty=0.5
# 字出現頻率施加懲罰，正值減少重複，負值鼓勵重複

MOK_top_p=0.9
# top_p  = 當 AI 準備說下一個字時，它會給所有可能的字打分數(機率）。0.1 = 這會讓說話非常嚴謹、死板、重複性高。0.9 = AI 會考慮總和達到 90% 的大量候選字。這會讓說話非常豐富、有創意、出人意料。

MOK_top_k=50
# top_k  = 當 AI 準備說下一個字時，它會給所有可能的字打分數(機率）。top_k=50 會讓 AI 只考慮分數最高的 50 個字。這會讓說話更嚴謹、重複性高，但仍有一定變化。top_k=0 則不限制候選字數量，完全由 temperature 和 top_p 控制隨機性。

# ================== 自動記憶檢索 ===================
# 數字越大，每次對話會取越多條記憶（建議 1~3）。重啟後生效。
MOK_MEMORY_RECALL_COUNT=3

# ================== Ollama設定 ===================
MOK_NUM_THREADS=2
# Ollama 允許的最大 CPU 執行緒數，根據你的 CPU 核心數調整(如 2、4、8）

# ================== 模型固定臺詞 ===================
MOK_start_msg=🎉 ${MokAgiName} 已成功部署並24小時線上！
MOK_welcome_msg=你好！我是有記憶的 AI 助手。
MOK_unAllowed_msg=您未獲得使用許可權。

ENV_TEMPLATE

    # 替換佔位符
    sed -i "s/__AGENT_NAME_PLACEHOLDER__/${AGENT_NAME_INPUT}/g" "${ENV_FILE}"

    echo -e "${YELLOW}=========================================="
    echo -e "請先編輯 ${ENV_FILE}，填入你的 Telegram Bot Token 和 Chat ID。"
    echo -e "       nano ${ENV_FILE}"
    echo -e ""
    echo -e "編輯完成後，Ctrl+X > 按 Y 儲存 > 再按 Enter "
    echo -e ""
    echo -e "，再執行指令碼:"
    echo -e "       bash ~/MokAgi0.sh"
    echo -e ""
    echo -e "==========================================${NC}"
    exit 0
elif [ ${#valid_configs[@]} -eq 1 ]; then
    # 只有一個設定檔，直接使用
    ENV_FILE="${valid_configs[0]}"
    echo -e "${GREEN}使用現有設定檔：${ENV_FILE}${NC}"
else
    # 多個設定檔，列出讓使用者選擇
    echo -e "${YELLOW}發現多個設定檔：${NC}"
    for i in "${!valid_configs[@]}"; do
        echo "  $((i+1))) $(basename "${valid_configs[$i]}")"
    done
    read -p "請選擇要使用的設定檔編號: " cfg_choice
    if [[ "$cfg_choice" =~ ^[0-9]+$ ]] && [ "$cfg_choice" -ge 1 ] && [ "$cfg_choice" -le ${#valid_configs[@]} ]; then
        ENV_FILE="${valid_configs[$((cfg_choice-1))]}"
        echo -e "${GREEN}選擇設定檔：${ENV_FILE}${NC}"
    else
        echo -e "${RED}無效選擇，退出。${NC}"
        exit 1
    fi
fi
# 清理 \r 字元並載入環境變數
tr -d '\r' < "${ENV_FILE}" > "${ENV_FILE}.clean"
mv "${ENV_FILE}.clean" "${ENV_FILE}"
export $(grep -v '^#' "${ENV_FILE}" | xargs) 2>/dev/null






















# ================== agent名稱 ===================
if [ -z "${AGENT_NAME}" ]; then
    AGENT_NAME="ai助手"
fi
mkdir -p "${PROJECT_DIR}/${AGENT_NAME}" # 建立知識庫


# ================== 檢查必填 Telegram Bot Token 是否已設定 ===================
if [ -z "${TG_TOKEN}" ] || [ "${TG_TOKEN}" = "你的Bot_Token" ]; then
    echo -e "${RED}❌ 錯誤：.env 中的 TG_TOKEN 未填寫或無效。${NC}"
    echo -e "${YELLOW}請編輯 ${ENV_FILE} 後重新執行指令碼。${NC}"
    exit 1
fi

# ================== 管理員 chat_id ===================
if [ -z "${ADMIN_CHAT_ID}" ]; then
    echo -e "${YELLOW}請輸入你的 Telegram Chat ID(可透過 @userinfobot 獲取）:${NC}"
    read -p "Admin Chat ID: " ADMIN_CHAT_ID
    echo "ADMIN_CHAT_ID=${ADMIN_CHAT_ID}" >> "${ENV_FILE}"
fi

# ================== 允許使用的使用者 ===================
if [ -z "${ALLOWED_USERS}" ]; then
    echo -e "${YELLOW}請輸入允許使用機器人的使用者 ID，多個用逗號分隔(留空則所有人可用）:${NC}"
    read -p "Allowed User IDs: " ALLOWED_USERS
    echo "ALLOWED_USERS=${ALLOWED_USERS}" >> "${ENV_FILE}"
fi

# ================== 模型設定 ===================
if [ -z "${MOK_MODEL_NAME}" ]; then
    MOK_MODEL_NAME="qwen3:1.7b"
    # 這裡指定 Ollama 模型名稱，可在 https://ollama.com/huihui_ai/qwen3-abliterated:1.7b 直接找其他模型
fi

if [ -z "${MOK_MODEL_api}" ]; then
    MOK_MODEL_api="http://localhost:11434/api/generate"
    # Ollama API 端點，保持不變
fi

if [ -z "${MOK_MAX_HISTORY_ROUNDS}" ]; then
    MOK_MAX_HISTORY_ROUNDS="6"
    # 對話歷史保留輪數，過多會增加上下文長度，過少則無記憶感
fi

if [ -z "${MOK_num_ctx}" ]; then
    MOK_num_ctx="16384"
    # 模型的上下文視窗大小(如 8192、16384）(32768 = 約 2.2 萬個中文字 / 40 到 50 頁 A4 紙滿滿的文字量）
fi

if [ -z "${MOK_num_predict}" ]; then
    MOK_num_predict="8192"
    # 模型的最大生成長度(如 2048、4096、8192）(8192 = 5,400 中文字 / 6 頁 A4 紙滿滿的文字量)
fi

if [ -z "${MOK_temperature}" ]; then
    MOK_temperature="0.8"
    # 溫度 / 隨機性(0 嚴謹, 1.0+ 創意)
fi

if [ -z "${MOK_repeat_penalty}" ]; then
    MOK_repeat_penalty="1.5"
    # 重複懲罰，防止鬼打牆(1.0:不懲罰，2.0:太高)
fi

if [ -z "${MOK_presence_penalty}" ]; then
    MOK_presence_penalty="0.6"
    # 字重複施加懲罰。正值增加新詞可能性，負值鼓勵重複
fi

if [ -z "${MOK_frequency_penalty}" ]; then
    MOK_frequency_penalty="0.5"
    # 字出現頻率施加懲罰，正值減少重複，負值鼓勵重複
fi

if [ -z "${MOK_top_p}" ]; then
    MOK_top_p="0.9"
    # top_p              = 當 AI 準備說下一個字時，它會給所有可能的字打分數(機率）。0.1 = 這會讓說話非常嚴謹、死板、重複性高。0.9 = AI 會考慮總和達到 90% 的大量候選字。這會讓說話非常豐富、有創意、出人意料。
fi

if [ -z "${MOK_top_k}" ]; then
    MOK_top_k="50"
    # top_k              = 當 AI 準備說下一個字時，它會給所有可能的字打分數(機率）。top_k=50 會讓 AI 只考慮分數最高的 50 個字。這會讓說話更嚴謹、重複性高，但仍有一定變化。top_k=0 則不限制候選字數量，完全由 temperature 和 top_p 控制隨機性。
fi
    # stop               = 生成這些字時，立即停止輸出。

# ================== 自動記憶檢索 ===================
# 數字越大，每次對話會取越多條記憶（建議 1~3）。重啟後生效。
if [ -z "${MOK_MEMORY_RECALL_COUNT}" ]; then
    MOK_MEMORY_RECALL_COUNT=3
fi

# ================== Ollama設定 ===================
if [ -z "${MOK_NUM_THREADS}" ]; then
    MOK_NUM_THREADS="2"
    # Ollama 允許的最大 CPU 執行緒數，根據你的 CPU 核心數調整(如 2、4、8）
fi

# ================== 模型固定臺詞 ===================
if [ -z "${MOK_start_msg}" ]; then
    MOK_start_msg="🎉 ${MokAgiName} 已成功部署並24小時線上！。"
fi
if [ -z "${MOK_welcome_msg}" ]; then
    MOK_welcome_msg="你好！我是有記憶的 AI 助手。"
fi
if [ -z "${MOK_unAllowed_msg}" ]; then
    MOK_unAllowed_msg="您未獲得使用許可權，請聯絡管理員。"
fi













echo -e "${GREEN}=========================================="
echo -e "${GREEN} 🦙 [2/8] 安裝 ollama "
echo -e "==========================================${NC}"
# 強制清除舊配置，確保重新建立
sudo rm -f /etc/systemd/system/ollama.service.d/override.conf
if ! command -v ollama &> /dev/null; then
    curl -fsSL https://ollama.com/install.sh | sh
fi
sudo mkdir -p /etc/systemd/system/ollama.service.d

#Environment="OLLAMA_HOST=[::]:11434" # 同時監聽 IPv4 和 IPv6
#Environment="OLLAMA_NUM_THREADS=2"      # 最多使用 2 個 CPU 執行緒
#Environment="OLLAMA_MAX_LOADED_MODELS=1" # 允許同時載入 1 個模型，節省 RAM
cat <<EOF | sudo tee /etc/systemd/system/ollama.service.d/override.conf
[Service]
Environment="OLLAMA_HOST=[::]:11434"
Environment="OLLAMA_NUM_THREADS=${MOK_NUM_THREADS}"
EOF
sudo systemctl daemon-reload
sudo systemctl restart ollama
sleep 5

















echo -e "${GREEN}=========================================="
echo -e " [3/8] 下載模型 ${MOK_MODEL_NAME} "
echo -e "==========================================${NC}"
# 定義環境變數以便在當前會話執行指令
export OLLAMA_HOST="[::]:11434"
# --- [下載 + 路徑檢查] ---
if ollama list | grep -q "^${MOK_MODEL_NAME} "; then
    echo -e "${YELLOW}模型 ${MOK_MODEL_NAME} 已存在，跳過下載。${NC}"
else
    echo "正在從 Ollama 庫拉取模型..."
    if ! ollama pull ${MOK_MODEL_NAME}; then
        echo ""
        echo "❌ 錯誤:模型路徑 [${MOK_MODEL_NAME}] 似乎不存在！"
        echo "------------------------------------------------"
        echo "這通常是因為:"
        echo "1. 模型名稱拼字錯誤(例如 _ 寫成 /）。"
        echo "2. 該模型在 Ollama 庫中已被刪除或設為私有。"
        echo "3. 網路無法連線至 Ollama 伺服器。"
        echo ""
        echo "📌 建議:請先在終端機手動輸入 'ollama search' 確認模型名稱，"
        echo "   或將指令碼開頭的 ${MOK_MODEL_NAME} 修改為官方版本 (如: qwen2.5:3b)。"
        echo ""
        echo "-- 終止指令碼，防止後續指令崩潰 --"
        echo "------------------------------------------------"
        exit 1
    fi
fi

# 將引數鎖定至 Ollama 模型中
cat > Modelfile <<EOF
FROM ${MOK_MODEL_NAME}
PARAMETER num_ctx ${MOK_num_ctx}
PARAMETER num_predict ${MOK_num_predict}
PARAMETER temperature ${MOK_temperature}
PARAMETER repeat_penalty ${MOK_repeat_penalty}
PARAMETER presence_penalty ${MOK_presence_penalty}
PARAMETER frequency_penalty ${MOK_frequency_penalty}
PARAMETER top_p ${MOK_top_p}
PARAMETER top_k ${MOK_top_k}
EOF
# 重新建立模型，把引數直接封裝進模型檔
ollama create ${MOK_MODEL_NAME} -f Modelfile
rm Modelfile

















echo -e "${GREEN}=========================================="
echo -e " [4/8] 安裝依賴... "
echo -e "==========================================${NC}"
sudo apt-get update -qq 2>/dev/null
sudo apt-get install -y -qq python3 python3-pip 2>/dev/null || true
pip install python-telegram-bot httpx --quiet














echo -e "${GREEN}=========================================="
echo -e " [5/8] 生成機器人執行主指令碼... "
echo -e "==========================================${NC}"
rm -f "${BOT_SCRIPT}"
cat > "${BOT_SCRIPT}" << PYEOF

import asyncio, logging, httpx, os, json, importlib.util, re, sys, subprocess
from collections import defaultdict
from telegram import Update, BotCommand
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# ================== 載入配置檔案（唯一資料來源）==================
def load_agent_config():
    agent_name = os.environ.get("AGENT_NAME")
    if not agent_name:
        proc_name = os.environ.get("PM2_PROGRAM_NAME") or sys.argv[0]
        match = re.search(r'${MokAgiName}_(.+)$', proc_name)
        agent_name = match.group(1) if match else "default"
    mokagi_name = "${MokAgiName}"
    config_path = os.path.join(os.path.expanduser("~"), f".{mokagi_name}", f".{agent_name}")
    if not os.path.exists(config_path):
        raise RuntimeError(f"配置檔案 {config_path} 不存在")
    config = {}
    with open(config_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, value = line.split('=', 1)
                config[key.strip()] = value.strip()
    return config, agent_name, mokagi_name

config, AGENT_NAME, MOKAGI_NAME = load_agent_config()
os.environ["AD_AGENT_NAME"] = AGENT_NAME
os.environ["AD_AgiName"] = MOKAGI_NAME

# 讀取所有必要配置（帶預設值）
TG_TOKEN = config.get("TG_TOKEN")
if not TG_TOKEN:
    raise RuntimeError("配置檔案中缺少 TG_TOKEN")
ADMIN_CHAT_ID = config.get("ADMIN_CHAT_ID", "")
ALLOWED_USERS_STR = config.get("ALLOWED_USERS", "")
ALLOWED_USERS = set()
if ALLOWED_USERS_STR:
    for uid in ALLOWED_USERS_STR.split(","):
        uid = uid.strip()
        if uid:
            ALLOWED_USERS.add(int(uid) if uid.isdigit() else uid)

OLLAMA_API = config.get("MOK_MODEL_api", "http://localhost:11434/api/generate")
MOK_MODEL_NAME = config.get("MOK_MODEL_NAME", "qwen3:1.7b")
MAX_HISTORY_ROUNDS = int(config.get("MOK_MAX_HISTORY_ROUNDS", 6))
MEMORY_RECALL_COUNT = int(config.get("MOK_MEMORY_RECALL_COUNT", 3))
MOK_num_ctx = int(config.get("MOK_num_ctx", 16384))
MOK_num_predict = int(config.get("MOK_num_predict", 8192))
MOK_temperature = float(config.get("MOK_temperature", 0.8))
MOK_top_p = float(config.get("MOK_top_p", 0.9))
MOK_top_k = int(config.get("MOK_top_k", 50))

# 固定引數
TIMEOUT = 300
PLUGIN_DIR = os.path.join(os.path.dirname(__file__), "tools")
GITHUB_TOOLS_REPO = "https://github.com/64071181/MokAgi/tree/main/tools"

logging.basicConfig(level=logging.INFO)

# 只會記錄 WARNING 及更高級別的日誌，而不再輸出 INFO 級別的 HTTP Request: POST ... getUpdates "HTTP/1.1 200 OK"
logging.getLogger("httpx").setLevel(logging.WARNING)

user_histories = defaultdict(list)
tools = {}

def sanitize(s: str) -> str:
    s = re.sub(r'[\u200b\u200c\u200d\u200e\u200f\ufeff]', '', s)
    s = ''.join(ch for ch in s if ch.isprintable() or ch in ('\n', '\t'))
    return s.strip()

def load_tools():
    global tools
    tools = {}
    if not os.path.isdir(PLUGIN_DIR):
        return
    for filename in os.listdir(PLUGIN_DIR):
        if filename.endswith(".py") and filename != "__init__.py":
            module_name = filename[:-3]
            try:
                spec = importlib.util.spec_from_file_location(module_name, os.path.join(PLUGIN_DIR, filename))
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                tools[module_name] = module
                logging.info(f"工具已載入: {module_name}")
            except Exception as e:
                logging.error(f"載入工具 {module_name} 失敗: {e}")

def get_plugin_commands():
    cmd_map = {}
    for mod in tools.values():
        if hasattr(mod, "PLUGIN_INFO"):
            info = mod.PLUGIN_INFO
            cmd_map[info["command"]] = getattr(mod, info["handler"], None)
    return cmd_map

def build_prompt(hist, new_msg):
    prompt = "以下是一個友好的中文助手和使用者的對話:\n\n"
    for h in hist:
        prompt += f"使用者:{h['user']}\n{AGENT_NAME}:{h['assistant']}\n"
    prompt += f"使用者:{new_msg}\n{AGENT_NAME}:"
    return prompt

async def query_ollama(chat_id, user_text):
    hist = user_histories[chat_id]
    memory_context = ""
    if "memory" in tools and hasattr(tools["memory"], "recall_memory"):
        try:
            recalled = await tools["memory"].recall_memory(
                chat_id, user_text, MEMORY_RECALL_COUNT, include_kb=True
            )
            if recalled:
                memory_context = f"【相關記憶與知識】\n{recalled}\n\n"
        except Exception as e:
            logging.warning(f"記憶檢索失敗: {e}")
    prompt = memory_context + build_prompt(hist, user_text)
    payload = {
        "model": MOK_MODEL_NAME,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_ctx": MOK_num_ctx,
            "num_predict": MOK_num_predict,
            "temperature": MOK_temperature,
            "top_p": MOK_top_p,
            "top_k": MOK_top_k,
        }
    }
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            resp = await client.post(OLLAMA_API, json=payload, timeout=120.0)
            resp.raise_for_status()
            data = resp.json()
            reply = data.get("response", "").strip()
            if reply.startswith("Thinking Process:") or reply.startswith("{"):
                reply = "抱歉，我一時沒理解你的意思，請再說一遍。"
            if reply:
                hist.append({"user": user_text, "assistant": reply})
                if len(hist) > MAX_HISTORY_ROUNDS:
                    hist.pop(0)
            else:
                reply = "(模型未返回內容）"
            return reply
        except Exception as e:
            logging.error(f"Ollama error: {e}")
            return "❌ 呼叫失敗，請稍後重試。"

async def start(update, context):
    await update.message.reply_text(config.get("MOK_welcome_msg", "你好！我是有記憶的 AI 助手。"))

async def clear_command(update, context):
    chat_id = update.message.chat_id
    user_histories[chat_id] = []
    await update.message.reply_text("記憶已清除，我們重新開始。")

async def handle_message(update, context):
    user_text = update.message.text
    chat_id = update.message.chat_id
    if ALLOWED_USERS and str(chat_id) not in map(str, ALLOWED_USERS):
        await update.message.reply_text(config.get("MOK_unAllowed_msg", "您未獲得使用許可權。"))
        return
    cmd_map = get_plugin_commands()
    for cmd, handler in cmd_map.items():
        if user_text == cmd or user_text.startswith(cmd + " "):
            args = user_text[len(cmd):].strip()
            temp_msg = await update.message.reply_text(f"⏳ 正在執行 {cmd} ...")
            try:
                result = await handler(args, str(chat_id))
                if isinstance(result, tuple):
                    text, markup = result
                    await context.bot.edit_message_text(
                        chat_id=temp_msg.chat_id,
                        message_id=temp_msg.message_id,
                        text=text,
                        reply_markup=markup,
                        parse_mode='HTML'
                    )
                elif result is not None:
                    await context.bot.edit_message_text(
                        chat_id=temp_msg.chat_id,
                        message_id=temp_msg.message_id,
                        text=result,
                        parse_mode='HTML'
                    )
                else:
                    await context.bot.edit_message_text("✅ 完成", chat_id=temp_msg.chat_id, message_id=temp_msg.message_id)
            except Exception as e:
                await context.bot.edit_message_text(f"❌ 工具執行錯誤: <pre>{e}</pre>", chat_id=temp_msg.chat_id, message_id=temp_msg.message_id,
                parse_mode='HTML')
            return

    # 嘗試多步任務分解
    multi_step_result = await execute_multi_step(chat_id, user_text)
    if multi_step_result:
        await update.message.reply_text(multi_step_result)
        return

    if "intent" in tools and hasattr(tools["intent"], "handle_intent"):
        handled = await tools["intent"].handle_intent(
            update, context, user_text, chat_id, cmd_map, tools,
            OLLAMA_API, MOK_MODEL_NAME
        )
        if handled:
            return



    # 如果分解失敗，才走普通聊天
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    
    # 步驟1：詢問 Ollama，同時告訴它有哪些工具可用
    tool_defs = build_tool_definitions()  # 收集所有工具的 tool_schema
    llm_raw_response = await query_ollama_with_tools(chat_id, user_text, tool_defs)

    # 步驟2：檢查 LLM 是否回傳了 tool_call JSON
    tool_call = extract_tool_call(llm_raw_response)

    if tool_call:
        tool_name = tool_call.get("name")
        tool_args = tool_call.get("arguments", {})

        handler = find_tool_handler(tool_name)
        if handler:
            # 執行工具，得到 JSON 結果
            raw_result = await handler(tool_args, str(chat_id))

            # 將工具結果送去自然化（轉成口語）
            reply = await naturalize_tool_result(chat_id, user_text, tool_name, raw_result)
        else:
            reply = f"❌ 找不到工具：{tool_name}"
    else:
        # 不是工具呼叫，直接使用 LLM 的文字回覆
        reply = llm_raw_response if llm_raw_response else "抱歉，我沒有理解你的意思。"

    # 將這輪對話記入歷史
    if reply:
        user_histories[chat_id].append({"user": user_text, "assistant": reply})

    await update.message.reply_text(reply)










async def update_bot_commands(app):
    base_commands = [
        BotCommand(sanitize("start"), sanitize("開始對話")),
        BotCommand(sanitize("clear"), sanitize("清除會話記憶")),
        BotCommand(sanitize("tools"), sanitize("工具箱")),
        BotCommand(sanitize("reload"), sanitize("更新")),
    ]
    plugin_commands = []
    for mod in tools.values():
        if hasattr(mod, "PLUGIN_INFO"):
            info = mod.PLUGIN_INFO
            cmd = sanitize(info["command"]).lstrip("/")
            desc = sanitize(info["description"])
            if cmd and desc:
                plugin_commands.append(BotCommand(cmd, desc))
    await app.bot.set_my_commands(base_commands + plugin_commands)

async def tools_command(update, context):
    text = "🧰 **已安裝的工具:**\n"
    for mod in tools.values():
        if hasattr(mod, "PLUGIN_INFO"):
            info = mod.PLUGIN_INFO
            text += f"  {info['command']} — {info['description']}\n"
    text += f"\n ➕  [增加工具]({sanitize(GITHUB_TOOLS_REPO)})"
    await update.message.reply_text(text, parse_mode="Markdown", disable_web_page_preview=True)

async def reload_tools_command(update, context):
    global tools
    tools = {}
    load_tools()
    await update_bot_commands(context.application)
    await update.message.reply_text(f"✅ 工具已載入，當前共有 {len(get_plugin_commands())} 個工具命令。")

async def send_welcome(app):
    if ADMIN_CHAT_ID:
        try:
            await app.bot.send_message(chat_id=ADMIN_CHAT_ID, text=config.get("MOK_start_msg", "🎉 ${MokAgiName} 已成功部署並24小時線上！"))
        except Exception as e:
            logging.warning(f"無法傳送歡迎訊息給 {ADMIN_CHAT_ID}: {e}")
























def build_tool_definitions():
    """從已載入的 tools 中，收集所有定義了 tool_schema 的工具"""
    defs = []
    for mod_name, mod in tools.items():
        if hasattr(mod, "PLUGIN_INFO") and "tool_schema" in mod.PLUGIN_INFO:
            defs.append(mod.PLUGIN_INFO["tool_schema"])
    return defs

def extract_tool_call(response_text):
    """嘗試從 LLM 回覆中提取 JSON tool_call"""
    try:
        if "{" in response_text and "}" in response_text:
            start = response_text.find("{")
            end = response_text.rfind("}") + 1
            json_str = response_text[start:end]
            data = json.loads(json_str)
            if "name" in data and "arguments" in data:
                return data
    except:
        pass
    return None

def find_tool_handler(tool_name):
    """根據 tool_schema 中的 name 找到對應的 handler"""
    for mod_name, mod in tools.items():
        if hasattr(mod, "PLUGIN_INFO"):
            schema = mod.PLUGIN_INFO.get("tool_schema", {})
            if schema.get("name") == tool_name:
                return getattr(mod, mod.PLUGIN_INFO.get("handler"), None)
    return None

async def query_ollama_with_tools(chat_id, user_text, tool_defs):
    """
    詢問 Ollama，同時在 prompt 中附上工具定義，
    讓模型判斷是否要輸出 tool_call JSON。
    """
    hist = user_histories[chat_id]
    memory_context = ""
    if "memory" in tools and hasattr(tools["memory"], "recall_memory"):
        try:
            recalled = await tools["memory"].recall_memory(
                chat_id, user_text, MEMORY_RECALL_COUNT, include_kb=True
            )
            if recalled:
                memory_context = f"【相關記憶與知識】\n{recalled}\n\n"
        except Exception as e:
            logging.warning(f"記憶檢索失敗: {e}")

    # 建立對話歷史 prompt
    prompt = build_prompt(hist, user_text)
    # 在前面附上記憶與工具定義
    full_prompt = memory_context + prompt

    # 如果提供了工具定義，在 prompt 中加入讓模型選擇工具的指引
    if tool_defs:
        tools_desc = json.dumps(tool_defs, ensure_ascii=False)
        full_prompt = (
            "你是一個智慧助手，可以呼叫以下工具來回答使用者。\n"
            "如果你需要呼叫工具，請只輸出一個 JSON 物件，格式如下：\n"
            '{"name": "工具名稱", "arguments": {...}}\n'
            "如果不需呼叫工具，請直接以中文回答。\n\n"
            f"可用的工具：{tools_desc}\n\n"
            + full_prompt
        )

    payload = {
        "model": MOK_MODEL_NAME,
        "prompt": full_prompt,
        "stream": False,
        "options": {
            "num_ctx": MOK_num_ctx,
            "num_predict": MOK_num_predict,
            "temperature": MOK_temperature,
            "top_p": MOK_top_p,
            "top_k": MOK_top_k,
        }
    }

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            resp = await client.post(OLLAMA_API, json=payload)
            resp.raise_for_status()
            data = resp.json()
            reply = data.get("response", "").strip()
            # 清理可能的思考標記
            if reply.startswith("Thinking Process:") or reply.startswith("{"):
                return reply
            return reply
        except Exception as e:
            logging.error(f"Ollama error: {e}")
            return "❌ 呼叫失敗，請稍後重試。"

async def naturalize_tool_result(chat_id, user_text, tool_name, raw_result):
    """將工具回傳的 JSON 結果，送給 LLM 轉成口語化的中文回答"""
    prompt = f"""你是一個友好的中文助手。使用者說：「{user_text}」

系統使用了工具「{tool_name}」並取得以下資訊：
{raw_result[:2000]}

請把這些資訊用自然的口語重新整理，像跟朋友聊天一樣告訴使用者。不要只列出資料。"""

    payload = {
        "model": MOK_MODEL_NAME,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_predict": 400,
            "temperature": 0.7,
            "top_p": 0.9,
            "top_k": 50,
        }
    }
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            resp = await client.post(OLLAMA_API, json=payload)
            data = resp.json()
            return data.get("response", raw_result)
        except:
            return raw_result

    











async def execute_multi_step(chat_id, user_text):
    """讓 LLM 將使用者複雜指令分解為多個工具呼叫並執行"""
    # 只給模型最多 4 步嘗試


    # 动态构建工具描述
    tool_descs = []
    cmd_map = get_plugin_commands()
    for cmd, handler in cmd_map.items():
        if cmd in ["/start", "/clear", "/tools", "/reload"]:
            continue  # 跳过基础命令
        # 找到对应的模块
        mod = None
        for name, m in tools.items():
            if hasattr(m, "PLUGIN_INFO") and m.PLUGIN_INFO.get("command") == cmd:
                mod = m
                break
        if not mod:
            continue
        info = mod.PLUGIN_INFO
        tool_name = info.get("tool_schema", {}).get("name", cmd.lstrip("/"))
        desc = info.get("description", "")
        # 构建参数格式说明（优先使用 tool_schema 中的定义）
        schema = info.get("tool_schema")
        if schema:
            params = schema.get("parameters", {}).get("properties", {})
            if params:
                param_desc = ", ".join([f'"{k}": {v.get("description","")}' for k, v in params.items()])
                args_format = f'args 為 {{ {param_desc} }}'
            else:
                args_format = "args 為字符串"
        else:
            # 没有 tool_schema 的用通用描述
            args_format = "args 為字符串，具體內容請參考工具說明"
        tool_descs.append(f"- {tool_name}: {desc}。{args_format}")

    tools_desc_text = "\n".join(tool_descs) if tool_descs else "暂无工具"

    prompt = f"""你是任務規劃助手。用戶的指令可能包含多個步驟。
請列出需要按順序調用的工具，用 JSON 數組表示，每一項包含 "name" 和 "args"。
如果只需一個工具，也返回數組格式。

可用工具及其參數格式：
{tools_desc_text}

用戶指令：{user_text}
只輸出一個純粹的 JSON 數組，不要包含任何解釋、註釋或多餘文字。"""






    payload = {
        "model": MOK_MODEL_NAME,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_predict": 300,
            "temperature": 0.2,
            "top_p": 0.9,
        }
    }
    try:
        async with httpx.AsyncClient(timeout=180) as client:
            resp = await client.post(OLLAMA_API, json=payload)
            resp.raise_for_status()
            text = resp.json().get("response", "").strip()


            # 提取 JSON 陣列
            # 穩健提取 JSON 陣列：嘗試只提取從第一個 '[' 到最後一個 ']' 的內容
            start = text.find('[')
            end = text.rfind(']') + 1
            if start == -1 or end == 0:
                return None

            json_candidate = text[start:end].strip()
            try:
                steps = json.loads(json_candidate)
            except json.JSONDecodeError:
                # 嘗試簡單的修復：將 {"xxx"} 這樣的錯誤物件轉為 "xxx" 字串
                import re
                def fix_invalid_args(match):
                    content = match.group(1)
                    # 如果物件內部只有一個不帶冒號的字串，說明是誤寫為物件了，直接提取字串
                    if re.fullmatch(r'\s*"[^"]+"\s*', content):
                        return '"' + content.strip().strip('"') + '"'
                    return match.group(0)
                
                # 匹配 "args": { ... } 中可能只有一個字串的情況
                fixed = re.sub(r'"args"\s*:\s*\{\s*("[^"]*")\s*\}', 
                               lambda m: f'"args": {m.group(1)}', 
                               json_candidate)
                try:
                    steps = json.loads(fixed)
                except:
                    # 如果還不行，嘗試其他修復策略
                    # 全域性替換中文標點
                    fixed2 = re.sub(r'[\u201c\u201d]', '"', json_candidate)
                    fixed2 = re.sub(r'[\uff1a]', ':', fixed2)
                    # 嘗試解析
                    try:
                        steps = json.loads(fixed2)
                    except:
                        logging.error(f"無法解析 JSON，原文: {text[:500]}")
                        return None

            if not isinstance(steps, list) or len(steps) == 0:
                return None
            # 按順序執行每一步
            collected = []
            cmd_map = get_plugin_commands()
            for step in steps:
                # 規範化 args 型別
                name = step.get("name")
                args = step.get("args")
                if name in ("admin", "memory") and isinstance(args, dict):
                    # 如果是意外物件，嘗試提取第一個值作為字串
                    if args:
                        first_val = next(iter(args.values()))
                        if isinstance(first_val, str):
                            step["args"] = first_val
                        else:
                            # 無法處理，跳過
                            continue
                elif name == "web_search" and isinstance(args, str):
                    # 如果是字串，轉換為帶 query 的物件
                    step["args"] = {"query": args}
                # 根據工具名獲取 handler
                if name == "admin":
                    handler = cmd_map.get("/admin")
                elif name == "web_search":
                    handler = cmd_map.get("/search")
                elif name == "memory":
                    handler = cmd_map.get("/memory")
                else:
                    handler = None
                if handler:
                    try:
                        if isinstance(args, dict):
                            result = await handler(args, str(chat_id))
                        else:
                            result = await handler(str(args), str(chat_id))
                        # 嘗試呼叫工具的自然化函式
                        naturalized_result = None
                        mod = find_module_by_command(name)  # 你需要寫一個輔助函式，根據工具名找到模組
                        if mod and hasattr(mod, "PLUGIN_INFO") and "naturalize_func" in mod.PLUGIN_INFO:
                            func = getattr(mod, mod.PLUGIN_INFO["naturalize_func"])
                            try:
                                naturalized_result = await func(
                                    user_text=user_text,
                                    raw_result=result,
                                    ollama_api=OLLAMA_API,
                                    model_name=MOK_MODEL_NAME
                                )
                            except:
                                pass
                        if naturalized_result:
                            collected.append(naturalized_result)
                        else:
                            collected.append(f"{name}: {str(result)[:200]}")
                    except Exception as e:
                        collected.append(f"工具 {name} 執行失敗：{e}")
                else:
                    collected.append(f"未找到工具 {name}")

            # 讓 LLM 總結所有結果
            summary_prompt = f"""使用者指令：{user_text}
工具執行結果：
{chr(10).join(collected)}

請用中文像朋友一樣告訴使用者結果。"""

            # 除錯日誌：輸出即將傳送的總結 prompt 前 300 字
            logging.info(f"Summary prompt (前300字)：{summary_prompt[:300]}")

            try:
                resp2 = await client.post(OLLAMA_API, json={
                    "model": MOK_MODEL_NAME,
                    "prompt": summary_prompt,
                    "stream": False,
                    "options": {"num_predict": 2000, "temperature": 0.7}
                }, timeout=180.0)
                resp2.raise_for_status()
                final_text = resp2.json().get("response", "").strip()
                logging.info(f"Final summary response：{final_text[:200]}")
                if final_text:
                    return final_text
                else:
                    logging.warning("Final summary 為空，使用拼接文字")
                    return "\n\n".join(collected)
            except Exception as summary_err:
                logging.exception("Final summary LLM 呼叫失敗")
                return "\n\n".join(collected)
    except Exception as e:
        logging.exception(f"多步執行失敗: {e}")
        return None








def find_module_by_command(cmd_name):
    # cmd_name 可能是 "admin", "web_search", "memory"
    # 需要對映到模組名，比如 "/admin" -> "admin", "/search" -> "web_search"
    for mod_name, mod in tools.items():
        if hasattr(mod, "PLUGIN_INFO"):
            if mod.PLUGIN_INFO.get("command") == f"/{cmd_name}":
                return mod
            # 特殊處理：web_search 的 command 是 /search
            if cmd_name == "web_search" and mod.PLUGIN_INFO.get("command") == "/search":
                return mod
            if cmd_name == "memory" and mod.PLUGIN_INFO.get("command") == "/memory":
                return mod
    return None








def main():
    load_tools()
    app = ApplicationBuilder().token(TG_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("clear", clear_command))
    app.add_handler(CommandHandler("tools", tools_command))
    app.add_handler(CommandHandler("reload", reload_tools_command))
    app.add_handler(MessageHandler(filters.TEXT, handle_message))
    asyncio.get_event_loop().run_until_complete(update_bot_commands(app))
    asyncio.get_event_loop().run_until_complete(send_welcome(app))
    print(f"✅ {AGENT_NAME} 啟動中... 傳送 /clear 可清空對話歷史")
    app.run_polling()

if __name__ == "__main__":
    main()
PYEOF













# ==============================================
# ==============================================
# ================ 安裝基本工具 =================
# ==============================================
# ==============================================
echo -e "${GREEN}=========================================="
echo -e " [6/8] 安裝基本工具... "
echo -e "==========================================${NC}"

# 長期記憶
curl -sL "${githubToolsUrl}/memory.py" -o "${toolsUrl}/memory.py"
# 自然語言意圖辨識
curl -sL "${githubToolsUrl}/intent.py" -o "${toolsUrl}/intent.py"
# 管理工具
curl -sL "${githubToolsUrl}/admin.py" -o "${toolsUrl}/admin.py"

















echo -e "${GREEN}=========================================="
echo -e "  [7/8] PM2 啟動... ${NC}"
echo -e "==========================================${NC}"
# 安裝 PM2 (如未安裝)
if ! command -v pm2 &> /dev/null; then
    curl -fsSL https://deb.nodesource.com/setup_18.x | sudo bash -
    sudo apt-get install -y nodejs
    sudo npm install -g pm2
fi





export AGENT_NAME="${AGENT_NAME}"
pm2 delete ${MokAgiName}_${AGENT_NAME} 2>/dev/null || true
pm2 start "${BOT_SCRIPT}" \
    --name ${MokAgiName}_${AGENT_NAME} \
    --interpreter python3 \
    --cwd "${PROJECT_DIR}"
pm2 save










# ==============================================
# ==============================================
# ================== 完成說明 ===================
# ==============================================
# ==============================================
# 設定開機自啟(只需在首次部署時手動確認 pm2 startup 的輸出）
#echo -e "\n${YELLOW}請複製並執行上方的 'sudo env PATH=...' 指令以啟用 PM2 開機自啟。${NC}"

echo -e "${GREEN}=========================================="
echo -e " 💖 [8/8] ${MokAgiName}_${AGENT_NAME} 部署完成！"
echo -e "=========================================="
echo ""
echo -e " ${MokAgiName}_${AGENT_NAME} 已啟動！ 檢視日誌: "
echo -e "    pm2 logs ${MokAgiName}_${AGENT_NAME} "
echo ""
echo -e " 💖 模型列表:"
echo -e "      ollama list "
echo ""
echo -e " 刪除指定模型 "
echo -e "     ollama rm mok_3b:latest "
echo ""
echo -e " 💖 檢視CPU:"
echo -e "      htop "
echo ""
echo -e " 如 CPU100% 強制清理所有 ollama runner"
echo -e "    sudo pkill -f 'ollama runner' "
echo ""


echo -e "==========================================${NC}"

