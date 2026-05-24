#!/usr/bin/env bash
# "start":"202604231241"
# ==============================================
# ================== 基礎設定 ===================
# ==============================================

# 先刪除舊的資料夾(如果有的話）
# rm -rf ~/.mok





set -o pipefail                       # 讓管道中任何一個命令失敗都會導致整個指令碼失敗
update_date="202605250320"              # 版本 | 更新日期（年月日時分）
MOKAGIName="mok"                      # 與 mokagi.py 中的 MOKAGI_home 一致
PROJECT_DIR="${HOME}/.${MOKAGIName}"  # ~/.mok
BOT_SCRIPT="${PROJECT_DIR}/mokagi.py" # 核心引擎（非直接啟動，僅供參考）

MOK_AGENT_NAME="default"
#  核心引擎 Github根路徑
GITHUB_REPO="https://github.com/64071181/MOKAGI"
GITHUB_REPO_RAW="https://raw.githubusercontent.com/64071181/MOKAGI/refs/heads/main"
# 工具庫
GITHUB_TOOLS_REPO="${GITHUB_REPO}/tree/main/tools"


# 核心文件路徑
CORE_FILES=("mokagi.py" "tool_handler.py" "recovery.py" "launcher.py")

# 前端文件路徑
FRONTEND_FILES=("frontends/mok_tg.py" "frontends/mok_web.py")

# 工具文件
TOOL_FILES=("memory.py" "intent.py" "admin.py" "workflow.py" "web_search.py" "web_fetch.py" "autofix.py")

# 網頁模板（位於 html/ 子目錄）
HTML_FILES=("index.html" "monitor.html" "ASCII.html")  # 根據實際需要

# 顏色定義
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'




echo -e "${GREEN}=========================================="
echo -e " 👼 [0/11] 開始安裝 mok_agi_${update_date}  👼"
echo -e "==========================================${NC}"



















echo -e "${GREEN}=========================================="
echo -e " [1/11] 環境設定 "
echo -e "==========================================${NC}"

mkdir -p "${PROJECT_DIR}"
mkdir -p "${PROJECT_DIR}/tools"
mkdir -p "${PROJECT_DIR}/frontends"
mkdir -p "${PROJECT_DIR}/html"
cd "${PROJECT_DIR}"

# 設置環境變數（供後續 Python 模塊使用）
export MOKAGI_HOME="${MOKAGIName}"
export PYTHONPATH="${PROJECT_DIR}:${PYTHONPATH}"























echo -e "${GREEN}=========================================="
echo -e " [2/11] 環境配置檔案 "
echo -e "==========================================${NC}"

shopt -s dotglob
configs=( "${PROJECT_DIR}"/.[!.]* )
shopt -u dotglob
valid_configs=()
for cfg in "${configs[@]}"; do
    [[ -f "$cfg" && "$(basename "$cfg")" != ".env" ]] && valid_configs+=("$cfg")
done

if [ ${#valid_configs[@]} -eq 0 ]; then
    echo -e "${YELLOW}請輸入此 Agent 的名稱（例如：joe、yun、sam）:${NC}"
    read -p "Agent 名稱: " MOK_AGENT_NAME_INPUT
    MOK_AGENT_NAME_INPUT=$(echo "$MOK_AGENT_NAME_INPUT" | xargs | cut -c1-32)
    if [ -z "$MOK_AGENT_NAME_INPUT" ]; then
        MOK_AGENT_NAME_INPUT="default"
    fi
    echo -e "${GREEN}建立配置檔範本 .${MOK_AGENT_NAME_INPUT} ...${NC}"
    curl -sL "${GITHUB_REPO_RAW}/env.env" -o "${PROJECT_DIR}/.${MOK_AGENT_NAME_INPUT}"
    # 替換佔位符（注意 env.env 中的 __MOK_AGENT_NAME_PLACEHOLDER__）
    sed -i "s/__MOK_AGENT_NAME_PLACEHOLDER__/${MOK_AGENT_NAME_INPUT}/g" "${PROJECT_DIR}/.${MOK_AGENT_NAME_INPUT}"
    MOK_AGENT_NAME="${MOK_AGENT_NAME_INPUT}"
elif [ ${#valid_configs[@]} -eq 1 ]; then
    ENV_FILE="${valid_configs[0]}"
    MOK_AGENT_NAME=$(get_agent_name "$ENV_FILE")
    echo -e "${GREEN}使用現有設定檔：${ENV_FILE}${NC}"
else
    echo -e "${YELLOW}發現多個設定檔：${NC}"
    for i in "${!valid_configs[@]}"; do
        echo "  $((i+1))) $(basename "${valid_configs[$i]}")"
    done
    read -p "請選擇要使用的主設定檔編號: " cfg_choice
    if [[ "$cfg_choice" =~ ^[0-9]+$ ]] && [ "$cfg_choice" -ge 1 ] && [ "$cfg_choice" -le ${#valid_configs[@]} ]; then
        ENV_FILE="${valid_configs[$((cfg_choice-1))]}"
        MOK_AGENT_NAME=$(get_agent_name "$ENV_FILE")
        echo -e "${GREEN}選擇設定檔：${ENV_FILE}${NC}"
    else
        echo -e "${RED}無效選擇，退出。${NC}"
        exit 1
    fi
fi

# 清理並載入環境變數
if [ -f "${ENV_FILE}" ]; then
    tr -d '\r' < "${ENV_FILE}" > "${ENV_FILE}.clean"
    mv "${ENV_FILE}.clean" "${ENV_FILE}"
    set -a
    source "${ENV_FILE}"
    set +a
fi















echo -e "${GREEN}=========================================="
echo -e " 🦙 [3/11] 安裝 ollama "
echo -e "==========================================${NC}"

if [ -z "${MOK_MODEL_NAME}" ]; then
    MOK_MODEL_NAME="qwen3:1.7b"
    # 這裡指定 Ollama 模型名稱，可在 https://ollama.com/huihui_ai/qwen3-abliterated:1.7b 直接找其他模型
fi

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
Environment="OLLAMA_NUM_THREADS=${MOK_NUM_THREADS:-2}"
EOF
sudo systemctl daemon-reload
sudo systemctl restart ollama
sleep 5


















echo -e "${GREEN}=========================================="
echo -e " [4/11] 下載模型 ${MOK_MODEL_NAME} "
echo -e "==========================================${NC}"
export OLLAMA_HOST="[::]:11434"
if ollama list | grep -q "^${MOK_MODEL_NAME} "; then
    echo -e "${YELLOW}模型 ${MOK_MODEL_NAME} 已存在，跳過下載。${NC}"
else
    echo "正在從 Ollama 庫拉取模型..."
    if ! ollama pull ${MOK_MODEL_NAME}; then
        echo -e "${RED}模型下載失敗，請檢查名稱或網絡。${NC}"
        exit 1
    fi
fi

# 鎖定模型參數
cat > Modelfile <<EOF
FROM ${MOK_MODEL_NAME}
PARAMETER num_ctx ${MOK_num_ctx:-16384}
PARAMETER num_predict ${MOK_num_predict:-8192}
PARAMETER temperature ${MOK_temperature:-0.8}
PARAMETER repeat_penalty ${MOK_repeat_penalty:-1.5}
PARAMETER presence_penalty ${MOK_presence_penalty:-0.6}
PARAMETER frequency_penalty ${MOK_frequency_penalty:-0.5}
PARAMETER top_p ${MOK_top_p:-0.9}
PARAMETER top_k ${MOK_top_k:-50}
EOF
ollama create ${MOK_MODEL_NAME} -f Modelfile
rm Modelfile


















echo -e "${GREEN}=========================================="
echo -e " [5/11] 安裝 Python 依賴... "
echo -e "==========================================${NC}"
sudo apt-get update -qq 2>/dev/null
sudo apt-get install -y -qq python3 python3-pip 2>/dev/null || true
pip install python-telegram-bot httpx flask flask-socketio watchdog openai --quiet















echo -e "${GREEN}=========================================="
echo -e " [6/11] 安裝核心 AI 引擎 ... "
echo -e "==========================================${NC}"
for file in "${CORE_FILES[@]}"; do
    curl -sL "${GITHUB_REPO_RAW}/${file}" -o "${PROJECT_DIR}/${file}"
done
















echo -e "${GREEN}=========================================="
echo -e " [7/11] 安裝基本工具... "
echo -e "==========================================${NC}"
for tool in "${TOOL_FILES[@]}"; do
    curl -sL "${GITHUB_REPO_RAW}/tools/${tool}" -o "${PROJECT_DIR}/tools/${tool}"
done
















echo -e "${GREEN}=========================================="
echo -e " [8/11] 安裝前端介面... "
echo -e "==========================================${NC}"
for front in "${FRONTEND_FILES[@]}"; do
    # 例如 frontends/mok_web.py
    curl -sL "${GITHUB_REPO_RAW}/${front}" -o "${PROJECT_DIR}/${front}"
done

# 下載網頁模板
for html in "${HTML_FILES[@]}"; do
    curl -sL "${GITHUB_REPO_RAW}/html/${html}" -o "${PROJECT_DIR}/html/${html}"
done

# 建立知識庫目錄
mkdir -p "${PROJECT_DIR}/chroma_data"

# AgentName目錄
mkdir -p "${PROJECT_DIR}/${MOK_AGENT_NAME}"

# 建立skill目錄
mkdir -p "${PROJECT_DIR}/skill"
















# ==============================================
# ==============================================
# ====== 生成反向隧道專用密鑰（GPU → CPU） =======
# ==============================================
# ==============================================

echo -e "${GREEN}=========================================="
echo -e " [9/11] 生成反向隧道專用密鑰（GPU → CPU） ... "
echo -e "==========================================${NC}"

Have_G_C_Key=false
REVERSE_KEY_DIR="/home/ubuntu/.ssh"
REVERSE_PRIVATE_KEY="$REVERSE_KEY_DIR/id_rsa_reverse"
REVERSE_PUBLIC_KEY="$REVERSE_PRIVATE_KEY.pub"

if [ ! -f "$REVERSE_PRIVATE_KEY" ]; then
    sudo -u ubuntu ssh-keygen -t rsa -b 4096 -N "" -f "$REVERSE_PRIVATE_KEY"
    echo "💖 反向隧道密鑰已生成：$REVERSE_PRIVATE_KEY"
else
    echo "💖 反向隧道密鑰已存在"
    Have_G_C_Key=true
fi
# 確保公鑰已添加到 authorized_keys（允許 GPU 機連接）
if ! grep -q "$(cat "$REVERSE_PUBLIC_KEY")" /home/ubuntu/.ssh/authorized_keys 2>/dev/null; then
    echo "📌 將公鑰添加到 authorized_keys..."
    cat "$REVERSE_PUBLIC_KEY" >> /home/ubuntu/.ssh/authorized_keys
    chmod 600 /home/ubuntu/.ssh/authorized_keys
    echo "💖 公鑰已添加"
else
    echo "💖 公鑰已存在於 authorized_keys"
fi














# ================== PM2 啟動 ==================
echo -e "${GREEN}=========================================="
echo -e "  [10/11] PM2 啟動 (統一進程 mok_agi) ${NC}"
echo -e "==========================================${NC}"
if ! command -v pm2 &> /dev/null; then
    curl -fsSL https://deb.nodesource.com/setup_18.x | sudo bash -
    sudo apt-get install -y nodejs
    sudo npm install -g pm2
fi

# 下載 launcher.py（如果不存在）
if [ ! -f "${PROJECT_DIR}/launcher.py" ]; then
    curl -sL "${GITHUB_REPO_RAW}/launcher.py" -o "${PROJECT_DIR}/launcher.py"
    chmod +x "${PROJECT_DIR}/launcher.py"
fi

# 停止並刪除舊的進程（避免衝突）
pm2 delete mok_agi 2>/dev/null || true

# 啟動統一啟動器
pm2 start "${PROJECT_DIR}/launcher.py" \
    --name "mok_agi" \
    --interpreter python3 \
    --cwd "${PROJECT_DIR}" \
    --log-date-format "YYYY-MM-DD HH:MM:SS"

pm2 save












# ================== 完成 ==================
echo -e "${GREEN}=========================================="
echo -e " 🎉 [11/11] mok_agi_${update_date} 部署完成！ 🎉"
echo -e "=========================================="
echo ""
echo -e " GITHUB:"
echo -e " ${GITHUB_REPO}"
echo ""
echo -e " 查看全部日誌: pm2 logs mok_agi"
echo -e " 重啟所有服務: pm2 restart mok_agi"
echo -e " 停止所有服務: pm2 stop mok_agi"
echo ""
echo -e " 模型列表:     ollama list"
echo -e " 強制清理:     sudo pkill -f 'ollama runner'"
echo ""
echo -e " 🌐 網頁界面訪問方式："
echo -e "    本機訪問： http://127.0.0.1:5000"
echo -e "    遠端訪問： http://<您的伺服器IP>:5000"
echo -e "    （請確保防火牆已開放 5000 埠，或使用 SSH 隧道）"
echo -e "    首次使用請先選擇左側 Agent，即可開始對話。"
echo ""
echo -e " 檢查模型隧道："
echo -e "              ss -tlnp | grep -E '11434|11435'"
echo ""
echo -e "==========================================${NC}"
