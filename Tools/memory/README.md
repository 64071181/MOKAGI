
    #!/usr/bin/env bash
    # 安装 ChromaDB 记忆插件
    PROJECT_DIR=~/.MokAgi
    PLUGIN_DIR="${PROJECT_DIR}/plugins"
    mkdir -p "${PLUGIN_DIR}"
    
    # 下载插件
    curl -sL https://raw.githubusercontent.com/64071181/MokAgi/refs/heads/main/Tools/memory/memory.py -o "${PLUGIN_DIR}/memory.py"
    
    # 安装依赖
    pip install chromadb -q
    
    # 热加载或提醒用户
    echo "✅ 记忆插件已安装！请在 Telegram 发送 /tools 確認。"
