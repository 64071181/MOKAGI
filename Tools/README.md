# 自製工具


    toolName
      |
       --- toolName.py(說明、主程式)

===

## 下載工具

     #!/usr/bin/env bash
    # 安裝 eaxmplo 
    PROJECT_DIR=~/.MokAgi
    PLUGIN_DIR="${PROJECT_DIR}/tools"
    mkdir -p "${PLUGIN_DIR}"
    
    # 下載工具
    curl -sL https://raw.githubusercontent.com/64071181/MokAgi/refs/heads/main/Tools/eaxmplo.py -o "${PLUGIN_DIR}/eaxmplo.py"
    
    # 安裝依賴
    ### {如有需要}
    
    # 加載
    echo "✅ eaxmplo 已安裝！請在 Telegram 發送 /reload 啟用。"


===

## toolName.py eaxmplo

    PLUGIN_INFO = {
        "command": "/eaxmplo",
        "icon":"😘",
        "description": "範本 (tool1, tool2)",
        "handler": "handle_eaxmplo",
        "intent_keywords": [
            ("範本1", "/tool1"),
            ("範本2", "/tool2"),
        ],
        "updata":"202604272310"
    }

    # ================== python code ===================
