# MOKAGI

> update : 202605250320  


> 自製最簡單的、可自我執行多步驟工作、可自我修改問題、自我升級的 AI Agent

## 一鍵部署（Ubuntu / Debian）

```bash
curl -sL https://raw.githubusercontent.com/64071181/MOKAGI/refs/heads/main/MOKAGI.sh -o ~/MOKAGI.sh && sed -i 's/\r//' ~/MOKAGI.sh && bash ~/MOKAGI.sh
```

## 部署完成後，您將擁有：

 - 一個 Ollama 本地模型服務（預設 qwen3:1.7b）

 - PM2 管理的統一進程 mok_agi（同時啟動 Telegram 機器人 + Web 界面）

 - 完整的工具插件系統（記憶、搜索、工作流、管理、自動修正等）

---

# 目錄結構

    /home/ubuntu/.mok/                      # MOKAGI_HOME 根目錄 (～/.mok)
    ├── launcher.py                         # 統一啟動器（掃描配置，啟動所有機器人 + Web）
    ├── mokagi.py                           # 核心 AI 引擎（對話、工具調用、工作流）
    ├── tool_handler.py                     # 工具加載與命令路由中間件
    ├── recovery.py                         # 意圖模糊恢復、錯誤處理
    ├── .<agent_name>                       # Agent 配置文件（隱藏文件）
    ├── <agent_name>/                       # 每個 Agent 的專屬目錄
    │   ├── workflows/                      # 工作流 JSON 與 report.md
    │   └── *.md                            # 知識庫文件（自動切塊存入 ChromaDB）
    ├── frontends/                          # 前端適配器 (可擴展)
    │   ├── mok_tg.py                       # Telegram 機器人（流式輸出）
    │   └── mok_web.py                      # Web + SocketIO 服務
    ├── tools/                              # 所有工具插件（動態加載）(可擴展)
    │   ├── admin.py                        # 管理命令（htop、切換模型、執行 shell 等）
    │   ├── autofix.py                      # 自動修正 Python 代碼錯誤
    │   ├── intent.py                       # 意圖識別引擎（規則 + LLM）
    │   ├── memory.py                       # 長期記憶（ChromaDB）與知識庫
    │   ├── web_search.py                   # 網頁搜索（DuckDuckGo + Tavily）
    │   ├── web_fetch.py                    # 網頁抓取（轉 Markdown）
    │   └── workflow.py                     # 多步驟工作流管理
    ├── skill/                              # 用戶自定義技能 (可擴展)
    ├── html/                               # Web 界面靜態文件
    │   ├── index.html                      # 主聊天界面（支持 Markdown 渲染）
    │   ├── monitor.html                    # 系統監控頁面
    └── chroma_data/                        # ChromaDB 向量數據（記憶 + 知識庫）


---

# 完整執行流程圖

                    用戶消息
                        │
        ┌───────────────┴───────────────┐
        │       0. pending_confirm?     │
        └───────────────┬───────────────┘
                  是 ↓         ↓ 否
             執行命令並返回  ┌───────────────────────┐
                            │ 0a. pending_clarify?  │
                            └───────────┬───────────┘
                                是 ↓         ↓ 否
                          合併理解並返回  ┌──────────────┐
                          確認或失敗      │ 1. 以 / 開頭?│
                                         └──────┬───────┘
                                          是 ↓     ↓ 否
                                     執行直接命令  ┌────────────┐
                                     並返回        │ 2. 意圖識別│
                                                  └─────┬──────┘
                                                        │
              ┌─────────────────────────┬───────────────┼───────────────┬─────────────────┐
              ↓                         ↓               ↓               ↓                 ↓
        cmd="chat"                其他命令           cmd=None        多步工作流標記      (其他保留)
              ↓                         ↓               ↓               ↓
      chat_with_tools              執行 handler    ask_clarification  execute_multi_step
      (記憶+LLM+工具調用)         自然化結果返回    存入_pending       逐步執行並返回
              ↓                         ↓               ↓
        返回普通回覆                 返回結果        返回提問



## 🔄 完整執行流程（`process_message` 統一入口）

| 階段 | 觸發條件 | 處理函數 / 模塊 | 輸出 / 下一步 |
|------|----------|----------------|----------------|
| 0. 待確認命令 | 存在 `_pending_confirm[user_id]` | 檢查用戶輸入是否為「確認/是/yes」 | ✅ 執行待確認命令 → 返回結果<br>❌ 清空狀態，繼續處理 |
| 0a. 待澄清意圖 | 存在 `_pending_clarify[user_id]` | `merge_and_reunderstand` 合併上下文 | ✅ 生成確認訊息 → 存入 `_pending_confirm` → 返回確認<br>❌ 返回「無法理解」 |
| 1. 直接命令 | 消息以 `/` 開頭 | `handle_direct_command` → `tool_handler.process_message` | 執行對應工具 → `naturalize_tool_result` → 返回結果 |
| 2. 意圖識別 | 非直接命令 | `recognize_intent`<br>（先規則匹配 `intent_keywords`，後 `llm_intent`） | 返回 `(cmd, args)` |
| 2a. 普通聊天 | `cmd == "chat"` | `chat_with_tools` | 記憶檢索 → 構建 prompt → `call_llm`<br>若 LLM 返回 `tool_call` → 執行工具並自然化<br>否則 → 普通回覆 → 儲存歷史 |
| 2b. 其他命令 | `cmd` 為具體工具名 | 執行對應 `handler(args, user_id)` → `naturalize_tool_result` | 返回工具執行結果（如搜索結果、記憶列表等） |
| 2c. 意圖模糊 | `cmd == None` | `ask_clarification` 生成提問 | 存入 `_pending_clarify` → 返回提問給用戶 |
| 3. 多步工作流 | LLM 返回 `"/workflow create"` 或前端收到 `WORKFLOW_AUTO_EXEC` | `execute_multi_step` → `auto_decompose_goal` 分解步驟 → 循環執行 | 逐步執行工作流 → 最終返回總結 |

> **注意**：多步工作流也可由用戶主動發送 `/workflow create 目標` 觸發，或在普通聊天中被 LLM 自動判斷為複雜任務後調用。

---

# 🧩 工具插件開發規範

所有工具位於 tools/ 目錄，每個工具必須定義 PLUGIN_INFO 字典，例如：

    PLUGIN_INFO = {
        "command": "/mycommand",            # Telegram 命令
        "icon": "🔧",                       # 圖示
        "handler": "handle_mycommand",      # 異步處理函數名
        "description": "工具描述",
        "intent_keywords": [                # 自然語言觸發詞
            ("關鍵詞", "/mycommand subcmd")
        ],
        "tool_schema": {                    # 供 LLM 自動調用的 JSON Schema
            "name": "my_tool",
            "description": "...",
            "parameters": {...}
        },
        "update":"202604272310"
        "naturalize_func": "naturalize_result"  # 可選：結果自然化函數
    }

工具實現後會自動被 tool_handler.load_tools() 加載，並注入到意圖識別、命令映射和 LLM 工具調用中。


## 🚀 常用管理命令（Telegram / Web 均支持）

| 命令 | 說明 |
|------|------|
| `/clear` | 清除當前會話的對話歷史（不影響長期記憶） |
| `/reload` | 重新加載所有工具插件（緊急重啟） |
| `/tools` | 列出所有已加載的工具 |
| `/admin htop` | 查看系統負載 |
| `/admin cpu` | 查看 CPU 使用率 |
| `/admin mode` | 查看當前模型及已安裝模型列表 |
| `/admin set_model <模型名>` | 切換 LLM 模型（自動重啟生效） |
| `/admin read_file <路徑> [行數]` | 讀取文件內容 |
| `/admin exec <shell命令>` | 執行任意 Shell 命令（需二次確認） |
| `/memory remember <內容>` | 記住一段信息 |
| `/memory recall <關鍵詞>` | 搜索相關記憶 |
| `/memory rebuild_kb` | 掃描 `~/.mok/<agent>/` 下的 `.md` 文件，重建知識庫 |
| `/search <關鍵詞> [d\|w\|m\|y]` | 網頁搜索（DuckDuckGo + Tavily） |
| `/fetch <URL>` | 抓取網頁內容並轉為 Markdown |
| `/workflow create <目標>` | 創建多步驟工作流（自動分解並執行） |
| `/workflow status` | 查看當前工作流進度 |
| `/autofix` | 自動修正 Python 代碼錯誤（提供原始碼和錯誤信息） |

---

# 🌐 Web 界面功能

    聊天：支持 Markdown 渲染、代碼高亮、流式輸出（思考過程與回覆分開顯示）

    文件瀏覽器：可查看 .mok、MOK_AI 等白名錄目錄內的文本文件和圖片/視頻

    系統監控：即時 CPU、內存、進程列表（/monitor）

    工具列表：展示所有已加載插件的命令與描述

    一鍵切換 Agent：左上角選擇不同配置（.溟、.沐 等），即時生效

    模型切換：在“設定”面板中選擇模型，自動保存到配置並重啟

===

# 📌 注意事項

    所有 Agent 配置為 ~/.mok/.<agent_name> 隱藏文件，格式為 key=value（支援註解 #）

    每個 Agent 有獨立的對話歷史（記憶）、工作流、知識庫（ChromaDB）

    重啟服務：pm2 restart mok_agi

    查看日誌：pm2 logs mok_agi

    若要完全卸載：pm2 delete mok_agi && rm -rf ~/.mok

===

# 🤝 擴展與自定義

    新增工具：在 tools/ 下創建 .py 文件，定義 PLUGIN_INFO 和對應的 handler 函數，執行 /reload 即可熱加載。

    新增前端：參考 frontends/mok_tg.py 或 mok_web.py，調用 mokagi.process_message() 並傳入 stream_callback。

    修改提示詞：直接編輯 mokagi.py 中的系統提示詞，或通過配置文件的 MOK_SYSTEM_PROMPT 覆蓋（需自行擴展）。