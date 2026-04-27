# admin 管理工具 (htop, ollama list, rm 等)

複製以下程式碼貼上主機執行即可


    #!/usr/bin/env bash
    # 管理工具 (htop, ollama list, rm 等)
    PROJECT_DIR=~/.MokAgi
    PLUGIN_DIR="${PROJECT_DIR}/tools"
    mkdir -p "${PLUGIN_DIR}"
    
    # 下載工具
    curl -sL https://raw.githubusercontent.com/64071181/MokAgi/refs/heads/main/Tools/admin/admin.py -o "${PLUGIN_DIR}/admin.py"
    
    # 加載
    echo "✅ 記憶工具已安裝！請在 Telegram 發送 /reload 啟用。"
