# intent 自然語言意圖辨識 (自動轉換指令，支援動態新增外掛)

複製以下程式碼貼上主機執行即可


    #!/usr/bin/env bash
    # 安裝 intent 自然語言意圖辨識 (自動轉換指令，支援動態新增外掛)
    PROJECT_DIR=~/.MokAgi
    PLUGIN_DIR="${PROJECT_DIR}/tools"
    mkdir -p "${PLUGIN_DIR}"
    
    # 下載工具
    curl -sL https://raw.githubusercontent.com/64071181/MokAgi/refs/heads/main/Tools/intent/intent.py -o "${PLUGIN_DIR}/intent.py"
    
    
    # 加載
    echo "✅ 自然語言意圖辨識 已安裝！請在 Telegram 發送 /reload 啟用。"
