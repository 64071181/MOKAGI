
# MokAgi AI 自主修復工作守則

> **適用場景**：AI 已部署在主機中，具備執行命令、讀取日誌、修改代碼的能力。  
> **目標**：遇到報錯或異常時，AI 能**主動診斷問題、定位根因、實施修復、驗證結果**，無需人工介入。

---

## 一、核心行動原則

發現問題 → 收集信息 → 定位根因 → 設計方案 → 實施修復 → 驗證結果 → 記錄經驗

每一步都必須有明確的**輸入、輸出和驗證標準**，避免盲目修改。

---

## 二、報錯診斷規程

### 2.1 收到報錯時，首先收集信息

| 信息來源 | 獲取方式 | 必查項 |
|----------|----------|--------|
| 用戶反饋 | 對話內容 | 完整的錯誤消息、觸發操作、預期結果 |
| Bot 日誌 | `pm2 logs MokAgi_溟 --lines 50`(假設現在anget是溟) | ERROR 級別日誌、異常堆棧 |
| 容器/服務狀態 | `docker ps -a`、`systemctl status ollama` | 關鍵服務是否運行 |
| 系統資源 | `free -h`、`df -h`、`top -bn1` | 內存、磁盤、CPU |

### 2.2 分析錯誤類型並匹配解決策略

| 錯誤類型 | 典型表現 | 診斷方法 | 解決策略 |
|----------|----------|----------|----------|
| **導入錯誤** | `ImportError: No module named 'xxx'` | 檢查是否安裝 | 提供安裝指引 `<pre>/admin pip install xxx</pre>` |
| **變量未定義** | `NameError: name 'xxx' is not defined` | 檢查 import 和變量作用域 | 添加缺失的 import 或修正變量作用域 |
| **屬性錯誤** | `AttributeError: 'xxx' object has no attribute 'yyy'` | 檢查對象類型與屬性 | 修正屬性名或對象類型 |
| **異步錯誤** | `object str can't be used in 'await' expression` | 檢查函數是否 async | 改為 `async def` 或移除多餘的 `await` |
| **連接失敗** | `All connection attempts failed` | 檢查目標服務狀態 | 啟動/重啟服務、檢查端口、檢查地址 |
| **容器退出** | `Exited (127)` 或 `Exited (1)` | 查看容器日誌 | 檢查配置、架構兼容性、資源限制 |
| **編碼/序列化錯誤** | `Object of type coroutine is not JSON serializable` | 檢查是否遺漏 `await` | 在異步調用前添加 `await` |
| **權限錯誤** | `Permission denied` | 檢查文件所有者 | 使用 `sudo` 或修改權限 |

---

## 三、代碼修改規程

### 3.1 修改代碼的檢查清單

在修改任何文件前，必須完成以下檢查：

| 檢查項 | 說明 |
|--------|------|
| 修改位置是否正確 | 確認文件名和路徑，檢查函數名和行號 |
| 影響範圍是否可控 | 只改必要的地方，避免連帶修改 |
| 是否添加了必要的 import | 新增的庫必須在文件頂部導入 |
| 異步/同步是否一致 | 調用異步函數必須用 `await` |
| 變量作用域是否正確 | 全局變量需聲明 `global`，局部變量不能跨函數 |

### 3.2 修改流程

1. 備份原文件（可選但推薦）
2. 編輯目標文件
3. 通過 `/reload` 指令重新加載工具
4. 測試修復效果
5. 如失敗，查看日誌並回滾或繼續修改

### 3.3 函數簽名規範

**普通工具 handler**：
```python
async def handle_xxx(args: Union[str, dict], chat_id: str = None) -> str:
```
- 返回字符串或 JSON 字符串

**自然化函數**（將 JSON 轉為口語）：
```python
async def naturalize_xxx(user_text, raw_result, ollama_api, model_name, temp_msg=None, context=None) -> str:
```

---

## 四、搜索工具專項診斷

### 4.1 搜索返回空結果

| 檢查點 | 命令/方式 |
|--------|-----------|
| Tavily API Key 是否配置 | 檢查配置文件 `~/.MokAgi/.溟` 中是否有 `TAVILY_API_KEY` |
| Tavily 庫是否安裝 | `pip list | grep tavily` |
| DuckDuckGo 庫是否安裝 | `pip list | grep duckduckgo` |
| 搜索 API 是否可達 | `curl` 測試 API 端點 |

### 4.2 搜索返回錯誤 JSON

- 查看原始 JSON 中的 `error` 或 `details` 字段
- 根據錯誤信息定位是 Tavily 還是 DuckDuckGo 失敗
- 如果兩個都失敗，檢查網絡連接和 API Key

### 4.3 搜索總結不自然（只顯示備用概括）

- 檢查 `naturalize_func` 是否正確定義在 `PLUGIN_INFO` 中
- 檢查自然化函數是否正確調用（查看日誌中的 `流式生成失敗` 或 `生成標題概括失敗`）
- 如果流式失敗，嘗試改用非流式請求（修改 `naturalize_search_result` 中的 `stream` 參數為 `False`）

---

## 五、常見錯誤速查表（本次對話經驗）

| 錯誤 | 根因 | 修復 | 涉及文件 |
|------|------|------|----------|
| `name 'subprocess' is not defined` | 缺少 import | 添加 `import subprocess` | web_search.py |
| `name 'httpx' is not defined` | 缺少 import | 添加 `import httpx` | web_search.py |
| `object str can't be used in 'await' expression` | 同步函數被 `await` 調用 | 函數定義改為 `async def` | memory.py, intent.py |
| `local variable 'msg' referenced before assignment` | `return msg` 寫在 `except` 塊外 | 將 `return msg` 縮進到 `except` 塊內 | web_search.py |
| `Can't parse entities: unsupported start tag` | HTML 標籤衝突 | 轉義尖括號或用 `html.escape` | admin.py |
| `All connection attempts failed` | 搜索服務未啟動或地址錯誤 | 啟動服務，驗證地址和端口 | web_search.py |
| `settings.yml: Is a directory` | 配置文件被錯誤創建為目錄 | 刪除目錄，用 `wget` 重新下載文件 | 服務器操作 |
| `Permission denied` 刪除配置文件 | 容器以 root 創建了文件 | `sudo rm -rf` 強制刪除 | 服務器操作 |
| Tavily API Key 未生效 | 配置文件未加載到環境變量 | 添加 `load_agent_config_value()` 讀取 | web_search.py |

---

## 六、修改後的驗證步驟

每次修改後，按順序驗證：

| 步驟 | 操作 | 檢查點 |
|------|------|--------|
| 1 | `/reload` | 確認工具加載成功，無錯誤提示 |
| 2 | 測試基礎命令 | `/search`、`/memory`、`/admin` 能否正常回應 |
| 3 | 測試自然語言觸發 | `搜尋 香港新聞` 等應觸發搜索並返回自然總結 |
| 4 | 查看原始 JSON | 檢查 `📄 原始結果` 消息中是否有數據 |
| 5 | 檢查總結質量 | 總結應包含口語化概括 + 完整鏈接列表 |
| 6 | 檢查日誌 | `pm2 logs MokAgi_溟 --lines 20` 無新增異常 |

---

## 七、配置管理規範

1. **每個 agent 的專屬配置文件**：`~/.MokAgi/.<agent名>`
2. **新增配置項**：直接在配置文件中添加 `KEY=VALUE` 行
3. **工具讀取配置**：使用 `load_agent_config_value(key)` 函數從配置文件讀取
4. **需要主程序全局導出的變量**：在 `MokAgi.py` 中添加 `os.environ["KEY"] = config.get("KEY", "")`
5. **不需要全局導出的**：工具自行通過 `load_agent_config_value()` 讀取

### `load_agent_config_value` 函數模板

```python
def load_agent_config_value(key: str) -> str:
    agent_name = os.environ.get("AD_AGENT_NAME", "")
    if not agent_name:
        return ""
    mokagi_name = os.environ.get("AD_AgiName", "MokAgi")
    config_path = os.path.join(os.path.expanduser("~"), f".{mokagi_name}", f".{agent_name}")
    if not os.path.exists(config_path):
        return ""
    try:
        with open(config_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    if k.strip() == key:
                        return v.strip()
    except Exception:
        pass
    return ""
```

---

## 八、工作日誌模板

每次修復後，生成如下格式的結構化日誌，便於後續覆盤：

```markdown
**時間**：2026-05-07  
**問題**：搜索返回空結果，無自然總結  
**根因**：Tavily 庫未安裝，且自然化函數失敗  
**修復**：
- 安裝 tavily-python 庫
- 修改 naturalize_search_result 改用非流式請求
**涉及文件**：web_search.py  
**驗證結果**：搜索正常，總結正常，鏈接完整  
**經驗總結**：新依賴需在搜索前檢查並提示安裝；流式請求不穩定時可回退非流式
```

---

## 九、核心設計理念（供 AI 理解系統）

1. **插件化架構**：每個功能獨立為 `.py` 文件，通過 `PLUGIN_INFO` 註冊命令、關鍵詞、自然化函數
2. **雙軌搜索**：併發調用 Tavily + DuckDuckGo，合併去重後返回
3. **漸進式自然化**：工具返回 JSON → 意圖系統查找工具自己的 `naturalize_func` → 調用該函數生成口語回覆
4. **配置隔離**：每個 agent 有自己的配置文件，工具可獨立讀取
5. **異步優先**：所有 handler 和自然化函數都應為 `async def`，避免阻塞事件循環

---

本守則基於 MokAgi 項目實際開發過程中積累的經驗編寫，涵蓋常見錯誤診斷、代碼修改規範、搜索工具專項處理、配置管理等方面。  
AI 在主機上自主操作時，應遵循本守則的流程逐步排查和修復問題，並能將新發現的經驗補充到速查表中。