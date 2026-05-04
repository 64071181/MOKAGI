
PLUGIN_INFO = {
    "command": "/memory",
    "icon":"🧠",
    "description": "長期記憶 (remember, recall, list, forgetall, chromadb)",
    "handler": "handle_memory",
    "intent_keywords": [
        ("更新知識", "/memory rebuild_kb"),

        ("顯示知識", "/memory list_kb"),

        ("記住", "/memory remember"),

        ("之前", "/memory recall"),

        ("回憶", "/memory list"),
    ],
    "updata":"202605041152"
}












import logging, os, re
import chromadb
from chromadb.config import Settings
import hashlib
from chromadb.utils import embedding_functions

# agent 名稱
mokagi_name = os.environ.get("AD_AgiName")
agent_name = os.environ.get("AD_AGENT_NAME", "default")

def sanitize_name_for_chromadb(raw_name: str) -> str:
    """使用哈希生成唯一且合规的 ChromaDB collection 名称"""
    import hashlib
    # 用 MD5 哈希确保不同名称生成不同字符串（长度固定，只含十六进制字符）
    hash_hex = hashlib.md5(raw_name.encode()).hexdigest()[:16]
    # 确保首字符为字母（ChromaDB 要求）
    return f"agent_{hash_hex}"

safe_agent_name = sanitize_name_for_chromadb(agent_name)

# 明確指定數據存儲路徑
CHROMA_PATH = os.path.join(os.path.expanduser("~"), f".{mokagi_name}", "chroma_data")
KNOWLEDGE_DIR = os.path.expanduser(f"~/.{mokagi_name}/{agent_name}")















'''
             %@*                            +.         #=     :@@-              
             @@-                            -@*        :@*    :@+               
            :@%                              *@#        @@  . :@+ -             
            +@=      .   .%-.......%@.        @@        #+ =@=:@+ +%            
            %@      =@=  .@@*******@@@        == :. %@@@@@@@@%+@+  @%           
           .@@******@@@* .@*       %@           :@@- .     -  :@+  =@=          
           =@:..@@:....  .@*       %@    :*********+ +=   :@%..@+   @+          
           %+   @@       .@*       %@                .@-  +@  .@+   :           
          -%    @@       .@*       %@           .     @@  #+  .@+               
          #.    @@       .@*       %@          .@@.   #%  %   .@+  .@-          
         -:     @@       .@*       %@     .+++++++=-==**=*#===*@%==%@@=         
                @@    :  .@*       %@              .::::::::::=@#:::::          
                @@   +@+ .@*       %@                          @*               
         =*****#@@#*#@@@*.@*       %@           @%   @=...-@%  @*  .:           
          .....:@@...... .@*       %@     .#####%%+  @%++++@@= @#  *@#          
                @#       .@*       %@                @+    @*  %@  @@           
               .@*       .@*       %@                @+    @*  #@ :@*           
               -@=       .@*       %@     .=    -%   @+    @*  +@ *@.           
               *@%=      .@*       %@     :@@%%%@@@  @@###%@*  -@+@#            
               @@ #%     .@*       %@     :@-   +@-  @+    @*  .@@@.            
              .@+  @@.   .@*       %@     :@-   +@.  @+    @*   @@*             
              +@   :@@   .@*       %@     :@-   +@.  @+    @*   @@              
              @#    *@#  .@*       %@     :@-   +@.  @*    @*  =@@.   :         
             +@      @@. .@*       %@     :@-   +@.  @@###%@* :@*@*   -         
             @-      =@: .@@*******@@     :@-   +@.  @+    @-.@= *@. :-         
            %+        -  .@#       %@     :@*---#@.  @+     .%:   @% *:         
           **            .@*       %@     :@*:::#@.  :     :#     =@@@.         
          *=             .@-       -      :@-   :-        =-       =@@*         
         =:                               .#             .          -@#         
'''

# ---------- 新增：Embedding 支援 ----------
try:
    from sentence_transformers import SentenceTransformer
    from chromadb.utils import embedding_functions
    EMBED_AVAILABLE = True
except ImportError:
    EMBED_AVAILABLE = False
    logging.warning("sentence-transformers 未安裝，知識庫功能將不可用")

# 使用 ChromaDB 官方的 SentenceTransformer 嵌入函數（自動處理模型下載與調用）
if EMBED_AVAILABLE:
    embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
else:
    embed_fn = None

# ---------- ChromaDB 初始化（保留原有 collection）----------
try:
    _client = chromadb.PersistentClient(path=CHROMA_PATH, settings=Settings(anonymized_telemetry=False))
    _collection = _client.get_or_create_collection(name=f"{safe_agent_name}_user_memory")   # 使用者記憶
    # 新增：知識庫 collection（獨立，使用 embedding）
    if EMBED_AVAILABLE:
        _kb_collection = _client.get_or_create_collection(
            name=f"{safe_agent_name}_room",
            embedding_function=embed_fn
        )
    else:
        _kb_collection = None
    MISSING_DEPS = False
except ImportError:
    MISSING_DEPS = True
    _collection = None
    _kb_collection = None

def _col():
    global _collection, _client
    if _collection is None:
        _client = chromadb.PersistentClient(
            path=CHROMA_PATH,
            settings=Settings(anonymized_telemetry=False)
        )
        _collection = _client.get_or_create_collection(name=f"{safe_agent_name}_user_memory")
    return _collection

# ---------- 新增：知識庫切塊函數（按標題 + 長度限制）----------
def chunk_markdown_by_headings(content: str, max_chars=500) -> list:
    """將 Markdown 文件按 # 標題分塊，每個塊包含標題及內容。返回 [{heading, content}]"""
    import re
    lines = content.split('\n')
    chunks = []
    current_heading = None
    current_content = []
    heading_re = re.compile(r'^(#{1,6})\s+(.+)$')

    def flush():
        nonlocal current_heading, current_content
        if current_heading is None or not current_content:
            return
        full_text = f"{current_heading}\n\n" + "\n".join(current_content).strip()
        if len(full_text) <= max_chars:
            chunks.append({"heading": current_heading, "content": full_text})
        else:
            # 長內容：再按段落切分
            para_text = "\n".join(current_content)
            paragraphs = re.split(r'\n\s*\n', para_text)
            buffer = ""
            for para in paragraphs:
                candidate = (buffer + "\n\n" + para).strip()
                if len(candidate) <= max_chars:
                    buffer = candidate
                else:
                    if buffer:
                        chunks.append({"heading": current_heading, "content": f"{current_heading}\n\n{buffer}"})
                    buffer = para
            if buffer:
                chunks.append({"heading": current_heading, "content": f"{current_heading}\n\n{buffer}"})
        current_heading = None
        current_content = []

    for line in lines:
        match = heading_re.match(line)
        if match:
            flush()
            current_heading = line.strip()
        else:
            if current_heading is not None:
                current_content.append(line)
            else:
                # 無標題內容（檔案開頭）
                if not chunks and not current_content:
                    current_heading = "(無標題)"
                current_content.append(line)
    flush()
    return chunks

def rebuild_knowledge_base():
    """掃描 room，將 .md 文件切塊後存入 _kb_collection"""
    if not EMBED_AVAILABLE or _kb_collection is None:
        return "❌ 知識庫功能未啟用，請安裝 sentence-transformers 並重啟。"

    if not os.path.exists(KNOWLEDGE_DIR):
        return f"❌ 知識庫目錄不存在，請建立 {KNOWLEDGE_DIR} 並放入 .md 檔案。"
    try:
        _kb_collection.delete(where={"source": "kb"})
    except:
        pass
    count = 0
    for filename in os.listdir(KNOWLEDGE_DIR):
        if not filename.endswith('.md'):
            continue
        filepath = os.path.join(KNOWLEDGE_DIR, filename)
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        chunks = chunk_markdown_by_headings(content, max_chars=500)
        for idx, chunk in enumerate(chunks):
            doc_text = chunk["content"]
            heading = chunk["heading"]
            doc_id = hashlib.md5(f"{filename}_{idx}_{heading}_{doc_text[:50]}".encode()).hexdigest()
            _kb_collection.add(
                documents=[doc_text],
                metadatas=[{"source": "kb", "file": filename, "heading": heading, "chunk_id": idx}],
                ids=[doc_id]
            )
            count += 1
    return f"✅ {agent_name} 已更新 {count} 個知識塊（按標題分塊）。"





























'''
                                              .                                 
                                             -@%.         %*                    
           **:....................#@-        -@=          .@%      .            
           *@*++++++++++++++++++++%@%        -@=           *@.    *@=           
           *@                     *@         -@=   :#######%@#####@@@-          
           *@                     *@         -@=      ::       -=               
           *@                     *@         -@=:      @#      %@%.             
           *@                     *@       + -@=-#     :@%    .@#               
           *@     +.        %=    *@       # -@= @+     %@    +#   -@:          
           *@     @@#######%@@+   *@       @ -@= *@+====%@+==+@*==+@@@-         
           *@     @%        @#    *@      .@ -@= =@-..................          
           *@     @%        @*    *@      +@ -@=  :  -            =.            
           *@     @%        @*    *@      @% -@=     @@**********#@@-           
           *@     @%        @*    *@     +@+ -@=     @%          :@#            
           *@     @%        @*    *@     :*  -@=     @#           @*            
           *@     @%        @*    *@         -@=     @%          :@*            
           *@     @%        @*    *@         -@=     @@++++++++++*@*            
           *@     @%        @*    *@         -@=     @#           @*            
           *@     @@:::::::=@*    *@         -@=     @#          .@*            
           *@     @@=======+@*    *@         -@=     @@###########@*            
           *@     @%        @*    *@         -@=     @+           *.            
           *@     @+        *     *@         -@=           *=                   
           *@                     *@         -@=    -  %#.  @#    =*            
           *@                     *@         -@=    # .@#   =@+    *@:          
           *@                     *@         -@=   .@ .@*    @@     @@.         
           *@                     *@         -@=   %# .@*    *#  :  =@#         
           *@%####################@@         -@=  %@- .@*        *   @@         
           *@.                    #@         -@= -@+  .@#.......-@-  +-         
           *@                     *@         -@=       @@@@@@@@@@@#             
           *#                     -:         -@-        --====--:.              
'''
# ---------- 修改 recall_memory 支援知識庫檢索 ----------
async def recall_memory(chat_id: int, query: str, n_results: int = 1, include_kb: bool = False) -> str:
    """
    原功能：檢索使用者記憶。
    若 include_kb=True 且知識庫可用，同時檢索知識庫，合併結果返回。
    """
    if MISSING_DEPS:
        return ""
    parts = []
    # 1. 使用者記憶（原有）
    try:
        col = _col()
        results = col.query(
            query_texts=[query],
            n_results=n_results,
            where={"chat_id": str(chat_id)}
        )
        docs = results.get("documents", [[]])[0]
        if docs:
            parts.append("【用戶記憶】\n" + "\n".join(docs))
    except Exception as e:
        logging.error(f"使用者記憶檢索錯誤: {e}")

    # 2. 知識庫檢索（新增）
    if include_kb and EMBED_AVAILABLE and _kb_collection:
        try:
            kb_results = _kb_collection.query(
                query_texts=[query],
                n_results=n_results,
                where={"source": "kb"}
            )
            kb_docs = kb_results.get("documents", [[]])[0]
            if kb_docs:
                parts.append("【知識庫】\n" + "\n\n---\n\n".join(kb_docs))
        except Exception as e:
            logging.error(f"知識庫檢索錯誤: {e}")

    return "\n\n".join(parts) if parts else ""






































'''
                           .                                                    
                @%+        @@=                                                  
               =@%         @%                =*.                 :@*            
               %@=         @%      ::        =@%*******@@%*******#@@#           
              .@@          @%      @@=       =@=       *@:        @#            
              =@* #%%%%%%%%@@%%%%%@@@@-      =@=       *@:        @*            
              %@           @%                =@=       *@:        @*            
             .@#           @%                =@=       *@:        @*            
             *@.           @%      :         =@=       *@:        @*            
             @@+   %*:::::=@@:::::*@*        =@=       *@:        @*            
            +@@:   %@=----=@@-----*@@:       =@#=======%@*=======+@*            
            @@@.   %@      @%     -@=        =@*::::::.#@+:::::::=@*            
           +#%@.   %@      @%     -@=        =@=       *@:        @*            
           @.*@.   %@      @%     -@=        =@=       *@:        @*            
          *- *@.   %@      @%     -@=        =@=       *@:        @*            
         .*  *@.   %@      @#     -@=        +@-       *@:        @*            
         =   *@.   %@+----+@%-----*@=        +@:       *@:        @*            
             *@.   %@-::::+@#:::::*@=        *@:       *@:        @*            
             *@.   %#     :@=     :%.        #@%#######@@%#######%@*            
             *@.     .    =@:                %@        #@=       :@*            
             *@.     +    #@                 @#        *@:        @*            
             *@.     .*   @#                 @+        *@:        @*            
             *@.      +# =@:                :@:        *@:        @*            
             *@.       ##@#                 +@         *@:        @*            
             *@.        @@+                 %*         *@:        @*            
             *@.       #@#@%-              .@          *@:        @*            
             *@.      ##  -@@@*-           *+          *@:        @*            
             *@.    -%-     +@@@@@*+-:.    %           *@:   -=+=*@*            
             *@.  -#=         -#@@@@@%    *.           *@:     :@@@-            
             *% =*-              :+%@.   ::            +*       #%=             
'''
# ---------- 原 handle_memory 保持不變，僅新增 rebuild_kb 分支 ----------
def handle_memory(args: str, chat_id: str = None):
    if MISSING_DEPS:
        msg = (
            "❌ 記憶工具缺少必要套件：`chromadb`、`sentence-transformers`\n\n"
            "請使用以下命令安裝（需要管理員權限）：\n"
            "<pre>/admin pip install chromadb sentence-transformers</pre>\n\n"
            "發送後會要求二次確認，輸入確認碼即可自動安裝。"
        )
        return msg
    if chat_id is None:
        return "❌ 無法識別使用者。"

    args = args.strip()
    if not args:
        help_text = f'''

📚 知識庫使用說明：
    (在 {mokagi_name} 目錄下建立 {agent_name} 資料夾，並放入 .md 檔案。)

    更新知識庫<pre>/memory rebuild_kb</pre>

    顯示知識庫<pre>/memory list_kb</pre>
=====
🧠 長期記憶使用說明：
    (使用下方按鈕快速操作，或直接輸入命令)

    <pre>/memory remember 內容</pre>
    例：/memory remember 我喜歡喝咖啡
    <pre>/memory recall 關鍵詞</pre>
    例：/memory recall 喜歡喝什麼

    列出所有記憶<pre>/memory list</pre>

    更新記憶<pre>/memory update 序號 新內容</pre>

    刪除記憶<pre>/memory delete 序號</pre>

    忘記所有記憶<pre>/memory forgetall</pre>

=====
🧩 自然語言意圖辨識：
        '''
        # 動態添加 intent_keywords（不轉義）
        for keyword, cmd in PLUGIN_INFO["intent_keywords"]:
            help_text += f'   "{keyword}" → {cmd}\n'
        return help_text

    parts = args.split(maxsplit=1)
    subcmd = parts[0].lower()
    content = parts[1] if len(parts) > 1 else ""

    try:
        col = _col()


        # 處理 remember 子命令
        if subcmd == "remember":
            if not content:
                return "用法: /memory remember 內容\n  例：/memory remember 我喜歡喝咖啡\n\n"
            # ----- 新增：人稱標準化 -----
            normalized = content
            # 移除開頭的「記得」或「記住」
            normalized = re.sub(r'^(?:記住)\s*', '', normalized)
            # 將「我」→「主人」
            normalized = re.sub(r'我', '主人', normalized)
            # 將「你/妳」→「agent_name」
            normalized = re.sub(r'你|妳', agent_name, normalized)
            # ------------------------------------------------------------------
            col.add(
                documents=[normalized],
                metadatas=[{"chat_id": chat_id}],
                ids=[f"{chat_id}_{col.count()}"]
            )
            return f"✅ {agent_name} 已記住 [{normalized}]"

        elif subcmd == "recall":
            if not content:
                return "用法: /memory recall 關鍵詞\n  例：/memory recall 喜歡喝什麼"
            results = col.query(
                query_texts=[content],
                n_results=3,
                where={"chat_id": chat_id}
            )
            docs = results.get("documents", [[]])[0]
            if not docs:
                return "沒有找到相關記憶。"
            reply = "🧠 回憶：\n"
            for d in docs:
                reply += f"· {d}\n"
            return reply

        elif subcmd == "list":
            results = col.get(
                where={"chat_id": chat_id},
                limit=10
            )
            docs = results.get("documents", [])
            if not docs:
                return "目前沒有任何記憶。"
            reply = "📋 最近記憶：\n=====================\n"
            for i, d in enumerate(docs):
                reply += f"\n========= {i+1} =========\n{d}\n=====================\n"
            return reply

        elif subcmd == "forgetall":
            col.delete(where={"chat_id": chat_id})
            return "🗑 記憶已清空。"

        elif subcmd == "delete":
            if not content:
                return "用法: <pre>/memory delete 序號</pre>\n  例：/memory delete 1\n\n先用 <pre>/memory list</pre> 查看序號。"
            try:
                idx = int(content) - 1
            except ValueError:
                return "序號必須是數字。"
            # 獲取該使用者的所有記憶（只取 id）
            all_mem = col.get(where={"chat_id": chat_id})
            ids = all_mem.get("ids", [])
            if idx < 0 or idx >= len(ids):
                return f"序號無效，請輸入 1 到 {len(ids)} 之間的數字。"
            target_id = ids[idx]
            col.delete(ids=[target_id])
            return f"✅ 已刪除第 {content} 條記憶。"

        elif subcmd == "update":
            parts = content.split(maxsplit=1)
            if len(parts) < 2:
                return "用法: <pre>/memory update 序號 新內容</pre>\n  例：/memory update 1 我是100歲"
            try:
                idx = int(parts[0]) - 1
            except ValueError:
                return "序號必須是數字。"
            new_content = parts[1]
            # 獲取該使用者的所有記憶（id 和 document）
            all_mem = col.get(where={"chat_id": chat_id})
            ids = all_mem.get("ids", [])
            docs = all_mem.get("documents", [])
            if idx < 0 or idx >= len(ids):
                return f"序號無效，請輸入 1 到 {len(ids)} 之間的數字。"
            target_id = ids[idx]
            old_doc = docs[idx]
            # 更新：先刪除舊的，再新增新的（ChromaDB 不支援直接修改 document）
            col.delete(ids=[target_id])
            # 新增時使用相同 id 可能會衝突，讓系統自動生成新 id
            new_id = f"{chat_id}_{col.count()}"
            col.add(
                documents=[new_content],
                metadatas=[{"chat_id": chat_id}],
                ids=[new_id]
            )
            return f"✅ 已將第 {parts[0]} 條記憶從「{old_doc}」更新為「{new_content}」。"

        # 新增：rebuild_kb 子命令
        elif subcmd == "rebuild_kb":
            return rebuild_knowledge_base()

        elif subcmd == "list_kb":
            if not EMBED_AVAILABLE or _kb_collection is None:
                return "❌ 知識庫功能未啟用或尚未重建。"
            try:
                # 取得所有知識庫文件（限制最多 50 條，避免輸出過長）
                results = _kb_collection.get(limit=50)
                docs = results.get("documents", [])
                metadatas = results.get("metadatas", [])
                if not docs:
                    return "知識庫中尚無任何區塊，請先執行 /memory rebuild_kb。"

                reply = "📚 知識庫區塊列表：\n=====================\n"
                for i, (doc, meta) in enumerate(zip(docs, metadatas)):
                    heading = meta.get("heading", "無標題")
                    source_file = meta.get("file", "未知檔案")
                    # 顯示標題、來源檔案以及內容前 60 個字元
                    preview = doc[:60].replace('\n', ' ')
                    reply += f"\n[{i+1}] {heading} (from {source_file})\n    {preview}...\n"
                return reply
            except Exception as e:
                logging.error(f"列出知識庫錯誤: {e}")
                return f"❌ 列出知識庫失敗: {e}"

        else:
            return f"未知子命令: {subcmd}"

    except Exception as e:
        logging.error(f"記憶工具錯誤: {e}")
        return f"❌ 記憶操作失敗: {e}"



