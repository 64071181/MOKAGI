

#!/usr/bin/env bash
# "start":"202604231241"
# "updata":"202605031933"
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

# ================== 檢查並準備環境配置文件 ===================
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
    # 配置文件名稱改為 .<agent名稱>
    ENV_FILE="${PROJECT_DIR}/.${AGENT_NAME_INPUT}"
    echo -e "${GREEN}將創建配置文件：${ENV_FILE}${NC}"
    
    # 生成配置文件，其中 AGENT_NAME 設為用戶輸入的名稱
    cat > "${ENV_FILE}" << 'ENV_TEMPLATE'
# MokAgi 環境變量配置（請填寫你的信息）
# 注意：等號前後不要加空格 " '

# agent名稱
AGENT_NAME=__AGENT_NAME_PLACEHOLDER__

# Telegram Bot Token
TG_TOKEN=你的Bot_Token

# 管理員 Chat ID（部署成功後會收到通知）
ADMIN_CHAT_ID=你的Telegram_Chat_ID

# 允許使用機器人的用戶 ID，多個用英文逗號分隔 (留空則所有人可用)
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
MOK_start_msg=🎉 MokAgi 已成功部署並24小時在線！
MOK_welcome_msg=你好！我是有記憶的 AI 助手。
MOK_unAllowed_msg=您未獲得使用權限。

ENV_TEMPLATE

    # 替换占位符
    sed -i "s/__AGENT_NAME_PLACEHOLDER__/${AGENT_NAME_INPUT}/g" "${ENV_FILE}"

    echo -e "${YELLOW}=========================================="
    echo -e "請先編輯 ${ENV_FILE}，填入你的 Telegram Bot Token 和 Chat ID。"
    echo -e "       nano ${ENV_FILE}"
    echo -e ""
    echo -e "編輯完成後，Ctrl+X > 按 Y 儲存 > 再按 Enter "
    echo -e ""
    echo -e "，再執行腳本:"
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
# 清理 \r 字符並載入環境變量
tr -d '\r' < "${ENV_FILE}" > "${ENV_FILE}.clean"
mv "${ENV_FILE}.clean" "${ENV_FILE}"
export $(grep -v '^#' "${ENV_FILE}" | xargs) 2>/dev/null






















# ================== agent名稱 ===================
if [ -z "${AGENT_NAME}" ]; then
    AGENT_NAME="ai助手"
fi
mkdir -p "${PROJECT_DIR}/${AGENT_NAME}" # 建立知識庫


# ================== 檢查必填 Telegram Bot Token 是否已設置 ===================
if [ -z "${TG_TOKEN}" ] || [ "${TG_TOKEN}" = "你的Bot_Token" ]; then
    echo -e "${RED}❌ 錯誤：.env 中的 TG_TOKEN 未填寫或無效。${NC}"
    echo -e "${YELLOW}請編輯 ${ENV_FILE} 後重新執行腳本。${NC}"
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
    MOK_start_msg="🎉 MokAgi 已成功部署並24小時在線！。"
fi
if [ -z "${MOK_welcome_msg}" ]; then
    MOK_welcome_msg="你好！我是有記憶的 AI 助手。"
fi
if [ -z "${MOK_unAllowed_msg}" ]; then
    MOK_unAllowed_msg="您未獲得使用權限，請聯繫管理員。"
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
import asyncio, logging, httpx, os, json, importlib.util, re

# tools 用
AD_AgiName = "${MokAgiName}"
os.environ["AD_AgiName"] = AD_AgiName

AD_AGENT_NAME = os.environ.get("AD_AGENT_NAME", "default")
#os.environ["AD_AGENT_NAME"] = AD_AGENT_NAME

def sanitize(s: str) -> str:
    """只移除不可見字符，保留所有正常文字（中英文等）"""
    # 移除零寬字符和 BOM
    s = re.sub(r'[\u200b\u200c\u200d\u200e\u200f\ufeff]', '', s)
    # 只刪除不可打印的控制字符（ASCII 0-31，除換行製表符外），保留所有可見文字
    s = ''.join(ch for ch in s if ch.isprintable() or ch in ('\n', '\t'))
    return s.strip()

from collections import defaultdict
from telegram import Update, BotCommand
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

TELEGRAM_TOKEN = os.environ.get("TG_TOKEN", "")
if not TELEGRAM_TOKEN:
    raise RuntimeError("未找到 TG_TOKEN，請在 .env 中設定")

# 主人/管理員 chat_id(用於傳送歡迎訊息）
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID", "").strip()

# 允許使用 bot 的使用者 chat_id 列表(逗號分隔）
ALLOWED_USERS_STR = os.environ.get("ALLOWED_USERS", "")
ALLOWED_USERS = set()
if ALLOWED_USERS_STR:
    for uid in ALLOWED_USERS_STR.split(","):
        uid = uid.strip()
        if uid:
            ALLOWED_USERS.add(int(uid) if uid.isdigit() else uid)

OLLAMA_API = "${MOK_MODEL_api}"
MOK_MODEL_NAME = "${MOK_MODEL_NAME}"
MAX_HISTORY_ROUNDS = ${MOK_MAX_HISTORY_ROUNDS}      # 保留最近 6 輪對話
TIMEOUT = 300
PLUGIN_DIR = os.path.join(os.path.dirname(__file__), "tools")
GITHUB_TOOLS_REPO = "${GITHUB_TOOLS_REPO}"

logging.basicConfig(level=logging.INFO)

# 每個使用者獨立的對話歷史:列表，每項為 {"user": "...", "assistant": "..."}
user_histories = defaultdict(list)

tools = {}
def load_tools():
    """動態載入外掛目錄下的所有 .py 檔案"""
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
                logging.info(f"外掛已載入: {module_name}")
            except Exception as e:
                logging.error(f"載入外掛 {module_name} 失敗: {e}")

def get_plugin_commands():
    """掃描外掛，返回命令 -> 處理函式 的對映"""
    cmd_map = {}
    for name, mod in tools.items():
        if hasattr(mod, "PLUGIN_INFO"):
            info = mod.PLUGIN_INFO
            cmd_map[info["command"]] = getattr(mod, info["handler"], None)
    return cmd_map



def build_prompt(hist: list, new_msg: str) -> str:
    """構建包含歷史的多輪 prompt"""
    prompt = "以下是一個友好的中文助手和使用者的對話:\n\n"
    for h in hist:
        prompt += f"使用者:{h['user']}\n{AD_AGENT_NAME}:{h['assistant']}\n"
    prompt += f"使用者:{new_msg}\n{AD_AGENT_NAME}:"
    return prompt

async def query_ollama(chat_id: int, user_text: str) -> str:
    hist = user_histories[chat_id]

    # 自動記憶檢索
    memory_recall_count = int(os.environ.get("MOK_MEMORY_RECALL_COUNT", "1"))
    memory_context = ""
    if "memory" in tools and hasattr(tools["memory"], "recall_memory"):
        try:
            # 每次都同時檢索知識庫與使用者記憶
            recalled = await tools["memory"].recall_memory(
                chat_id, user_text, memory_recall_count, include_kb=True
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
            "num_ctx": ${MOK_num_ctx},
            "num_predict": ${MOK_num_predict},
            "temperature": ${MOK_temperature},
            "top_p": ${MOK_top_p},
            "top_k": ${MOK_top_k},
        }
    }

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            resp = await client.post(OLLAMA_API, json=payload)
            resp.raise_for_status()
            data = resp.json()
            reply = data.get("response", "").strip()

            # 清理可能的思考過程殘留
            if reply.startswith("Thinking Process:") or reply.startswith("{"):
                # 如果模型吐出奇怪內容，回退提示
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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("${MOK_welcome_msg}")

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    user_histories[chat_id] = []
    await update.message.reply_text("記憶已清除，我們重新開始。")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    chat_id = update.message.chat_id
    # 如果設定了允許列表，且當前使用者不在列表中，則忽略(可選回覆提示）
    if ALLOWED_USERS and str(chat_id) not in map(str, ALLOWED_USERS):
        await update.message.reply_text("${MOK_unAllowed_msg}")
        return

    cmd_map = get_plugin_commands()

    # 檢查是否為外掛命令
    for cmd, handler in cmd_map.items():
        if user_text == cmd or user_text.startswith(cmd + " "):
            args = user_text[len(cmd):].strip()
            # 發送臨時訊息
            temp_msg = await update.message.reply_text(f"⏳ 正在執行 {cmd} ...")
            try:
                result = handler(args, str(chat_id))
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
                    await context.bot.edit_message_text(
                        "✅ 完成",
                        chat_id=temp_msg.chat_id,
                        message_id=temp_msg.message_id
                    )
            except Exception as e:
                await context.bot.edit_message_text(
                    f"❌ 外掛執行錯誤: {e}",
                    chat_id=temp_msg.chat_id,
                    message_id=temp_msg.message_id
                )
            return

    # 自然語言意圖處理
    if "intent" in tools and hasattr(tools["intent"], "handle_intent"):
        handled = await tools["intent"].handle_intent(
            update, context, user_text, chat_id, cmd_map, tools,
            OLLAMA_API, MOK_MODEL_NAME   # 傳入主程式的 Ollama API 與模型名稱
        )
        if handled: return


    # 普通對話
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    reply = await query_ollama(chat_id, user_text)
    if len(reply) > 4000:
        for i in range(0, len(reply), 4000):
            await update.message.reply_text(reply[i:i+4000])
    else:
        await update.message.reply_text(reply)


async def update_bot_commands(app):
    """根據已安裝外掛動態更新 TG 命令選單"""
    base_commands = [
        BotCommand(sanitize("start"), sanitize("開始對話")),
        BotCommand(sanitize("clear"), sanitize("清除會話記憶")),
        BotCommand(sanitize("tools"), sanitize("工具箱")),
        BotCommand(sanitize("reload"), sanitize("更新")),
    ]

    plugin_commands = []
    for name, mod in tools.items():
        if hasattr(mod, "PLUGIN_INFO"):
            info = mod.PLUGIN_INFO
            cmd = sanitize(info["command"]).lstrip("/")
            desc = sanitize(info["description"])
            if cmd and desc:
                plugin_commands.append(BotCommand(cmd, desc))
    await app.bot.set_my_commands(base_commands + plugin_commands)
    print(f"✅ 已同步 {len(base_commands) + len(plugin_commands)} 個命令")


async def tools_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "🧰 **已安裝的工具:**\n"
    plugin_count = 0
    for name, mod in tools.items():
        if hasattr(mod, "PLUGIN_INFO"):
            info = mod.PLUGIN_INFO
            text += f"  {info['command']} — {info['description']}\n"
            plugin_count += 1
    if plugin_count == 0:
        text += "  暫無已安裝的工具。\n"
    text += f"\n ➕  [增加工具]({sanitize(GITHUB_TOOLS_REPO)})"
    await update.message.reply_text(text, parse_mode="Markdown", disable_web_page_preview=True)

async def reload_tools_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """已更新所有工具及新命令菜單"""
    # 重新加載工具
    global tools
    tools = {}
    load_tools()

    # 動態刷新 TG 命令菜單
    await update_bot_commands(context.application)

    # 通知用戶
    new_count = len(get_plugin_commands())
    await update.message.reply_text(f"✅ 工具已加載，當前共有 {new_count} 個工具命令。")

async def send_welcome(app):
    if ADMIN_CHAT_ID:
        try:
            await app.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text="${MOK_start_msg}"
            )
        except Exception as e:
            logging.warning(f"無法傳送歡迎訊息給 {ADMIN_CHAT_ID}: {e}")

def main():
    load_tools()
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("clear", clear_command))
    app.add_handler(CommandHandler("tools", tools_command))
    app.add_handler(CommandHandler("reload", reload_tools_command))
    app.add_handler(MessageHandler(filters.TEXT, handle_message))
    asyncio.get_event_loop().run_until_complete(update_bot_commands(app))
    # 傳送歡迎訊息
    asyncio.get_event_loop().run_until_complete(send_welcome(app))
    print("✅ ${AGENT_NAME} 啟動中... 傳送 /clear 可清空對話歷史")
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




export AD_AGENT_NAME="${AGENT_NAME}"
export AD_AgiName="${MokAgiName}"
export TG_TOKEN="${TG_TOKEN}"
export ADMIN_CHAT_ID="${ADMIN_CHAT_ID}"
export ALLOWED_USERS="${ALLOWED_USERS}"
export MOK_MODEL_NAME="${MOK_MODEL_NAME}"
export MOK_MODEL_api="${MOK_MODEL_api}"
export MOK_MEMORY_RECALL_COUNT="${MOK_MEMORY_RECALL_COUNT}"


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
echo -e " 💖 查看CPU:"
echo -e "      htop "
echo ""
echo -e " 如 CPU100% 強制清理所有 ollama runner"
echo -e "    sudo pkill -f 'ollama runner' "
echo ""


echo -e "==========================================${NC}"

