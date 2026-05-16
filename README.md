# MOKAKI

# "updata":"202605170422"

自製最簡單的 ai agent

複製以下程式碼貼上主機執行即可

    curl -sL https://raw.githubusercontent.com/64071181/MOKAGI/refs/heads/main/MOKAGI.sh -o ~/MOKAGI.sh && sed -i 's/\r//' ~/MOKAGI.sh && bash ~/MOKAGI.sh



===

# 目錄結構

/home/ubuntu/.mok/                    # MOKAGI_home 根目錄
|
├── README.md                         # 說明文件
├── mokagi.py                         # 核心 AI 引擎
├── tool_handler.py                   # 工具加載中間件
├── .AgentName                        # 環境配置檔案
|
├── AgentName/                        # AgentName目錄
│   └── workflows/                    # 工作流目錄
|
├── frontends/                        # 前端介面目錄
│   ├── __init__.py                   # 可選，空文件
│   ├── mok_tg.py                     # Telegram 適配器
│   └── mok_web.py                    # 網頁適配器
|
├── tools/                            # 插件工具目錄
│   ├── __init__.py                   # 可選，空文件
│   ├── admin.py                      # 管理員工具
│   ├── memory.py                     # 記憶體管理工具
│   ├── intent.py                     # 意圖管理工具
│   └── workflow.py                   # 工作流工具
|
├── skill/                            # 技能目錄
|
├── html/                             # 網頁介面
│   ├── index.html                    # 主頁
│   └── monitor.html                  # 監控頁
|
└── chroma_data/                      # ChromaDB 向量數據（自動生成）


===