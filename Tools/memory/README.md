
    #!/usr/bin/env bash
    # 安裝 ChromaDB 記憶插件
    PROJECT_DIR=~/.MokAgi
    PLUGIN_DIR="${PROJECT_DIR}/plugins"
    mkdir -p "${PLUGIN_DIR}"
    
    # 下載插件
    curl -sL https://raw.githubusercontent.com/64071181/MokAgi/refs/heads/main/Tools/memory/memory.py -o "${PLUGIN_DIR}/memory.py"
    
    # 安裝依賴
    pip install chromadb -q
    
    # 熱加載
    echo "✅ 記憶插件已安裝！請在 Telegram 發送 /reload 啟用。"
