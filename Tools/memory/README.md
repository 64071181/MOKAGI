# chromadb 記憶工具

複製以下程式碼貼上主機執行即可


    #!/usr/bin/env bash
    # 安裝 ChromaDB 記憶工具
    PROJECT_DIR=~/.MokAgi
    PLUGIN_DIR="${PROJECT_DIR}/tools"
    mkdir -p "${PLUGIN_DIR}"
    
    # 下載工具
    curl -sL https://raw.githubusercontent.com/64071181/MokAgi/refs/heads/main/Tools/memory/memory.py -o "${PLUGIN_DIR}/memory.py"
    
    # 安裝依賴
    pip install chromadb -q
    
    # 加載
    echo "✅ 記憶工具已安裝！請在 Telegram 發送 /reload 啟用。"
