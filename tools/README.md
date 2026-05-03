# "updata":"202605040059"

# 自製工具

    tools
      |
       --- toolName.py(說明、主程式)

===

## 下載工具 (cmd)

    curl -sL https://raw.githubusercontent.com/64071181/MokAgi/refs/heads/main/tools/eaxmplo.py -o "~/.MokAgi/tools/eaxmplo.py"

===

## eaxmplo.py

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

    # if need pip install
    try:
        import chromadb
        print("chromadb 已安装，版本：", chromadb.__version__)
    except ImportError:
        msg = (
                    "❌ need pip install：`chromadb`、`sentence-transformers`\n\n"
                    "請使用以下命令安裝（需要管理員權限）：\n"
                    "<pre>/admin pip install chromadb sentence-transformers</pre>\n\n"
                    "發送後會要求二次確認，輸入確認碼即可自動安裝。"
                )
        return msg

    # ================== python code ===================


