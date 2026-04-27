# 自製工具


toolName
  |
   --- README.md(說明、一鍵安裝)
  |
   --- toolName.py(說明、主程式)

===

## README.md eaxmplo

     #!/usr/bin/env bash
    # 安裝 ChromaDB 記憶工具
    PROJECT_DIR=~/.MokAgi
    PLUGIN_DIR="${PROJECT_DIR}/tools"
    mkdir -p "${PLUGIN_DIR}"
    
    # 下載工具
    curl -sL https://raw.githubusercontent.com/64071181/MokAgi/refs/heads/main/Tools/eaxmplo/eaxmplo.py -o "${PLUGIN_DIR}/memory.py"
    
    # 安裝依賴
    ### {如有需要}
    
    # 加載
    echo "✅ 記憶工具已安裝！請在 Telegram 發送 /reload 啟用。"


===

## toolName.py eaxmplo

    PLUGIN_INFO = {
        "command": "/memory",
        "description": "長期記憶 (remember, recall, list, forgetall)",
        "handler": "handle_memory",
        "updata":"202604272310"
    }
    
    # python code
