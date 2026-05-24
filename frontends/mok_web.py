"""
mok_web.py
網頁前端適配器（基於 mokagi）
提供文件瀏覽器、系統監控、聊天界面，所有 AI 對話能力調用 mokagi 模塊。
202605250320
"""

import os, sys
import re
import json
import asyncio
import threading
import time
from flask import Flask, render_template, request, send_from_directory
from flask_socketio import SocketIO
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

import sqlite3
from contextlib import closing

# 導入核心模塊
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ['AD_MOK_AGENT_NAME'] = 'default'
import mokagi
from mokagi import process_message, clear_history, reload_tools, MOKAGI_home

# 導入工具管理（用於獲取工具列表等）
import tool_handler

# 啟動時加載工具
tool_handler.load_tools()

# 定義模板目錄
template_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'html')
app = Flask(__name__, template_folder=template_dir)
app.config['SECRET_KEY'] = 'secret_dev_key'
socketio = SocketIO(app, cors_allowed_origins="*")

# ---------- 文件瀏覽相關（動態白名單）----------
WATCH_PATH = "/home/ubuntu/"
# 白名單使用動態 home 目錄名稱
ALLOWED_PATHS = (
    f'.{MOKAGI_home}',          # .mok
    'MOK_AI',
    '.openclaw/workspace',
    '.openclaw/agents',
    '.openclaw/cron',
    '.openclaw/skills',
    '.openclaw/openclaw.json',
    '.hermes/SOUL.md',
    '.hermes/config.yaml',
    '.hermes/skills'
)
ALLOWED_ITEMS_LIST = list(ALLOWED_PATHS)

class FileChangeHandler(FileSystemEventHandler):
    def __init__(self, socketio_instance):
        self.socketio = socketio_instance
        self.ALLOWED_PREFIXES = ALLOWED_PATHS

    def on_any_event(self, event):
        if event.is_directory:
            return
        rel_path = os.path.relpath(event.src_path, WATCH_PATH)
        if rel_path.startswith(self.ALLOWED_PREFIXES) and not rel_path.endswith('.tmp'):
            self.socketio.emit('file_change', {'path': rel_path})

def get_file_tree(path):
    tree = []
    try:
        current_path = os.path.normpath(path)
        base_path = os.path.normpath(WATCH_PATH)
        if current_path == base_path:
            items = [item for item in ALLOWED_PATHS if os.path.exists(os.path.join(current_path, item))]
        else:
            items = sorted([f for f in os.listdir(current_path)])   # 不再過濾隱藏文件
    except PermissionError:
        return []
    for item in items:
        if 'web_viewer' in item:
            continue
        full_path = os.path.join(current_path, item)
        is_dir = os.path.isdir(full_path)
        node = {'name': item, 'path': os.path.relpath(full_path, WATCH_PATH), 'is_dir': is_dir}
        if is_dir:
            node['children'] = get_file_tree(full_path)
        tree.append(node)
    return tree

# ---------- 數據庫（聊天曆史，僅用於前端展示）----------
DB_PATH = os.path.expanduser(f"~/.{MOKAGI_home}/chat_history.db")

def init_db():
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT,
                think_content TEXT,
                timestamp REAL NOT NULL
            )
        ''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_agent ON chat_history (agent)')
        conn.commit()

init_db()

# ---------- 多 Agent 支持（配置文件切換）----------
ENV_DIR = os.path.expanduser(f"~/.{MOKAGI_home}")
DOT_MING_PATH = os.path.expanduser(f"~/.{MOKAGI_home}/.default")
CURRENT_ENV_PATH = DOT_MING_PATH

def parse_dot_ming():
    """解析 .default 文件，返回配置字典和模型列表（與 mokagi 配置同步）"""
    global MOK_CONFIG
    config = {}
    models = []
    if not os.path.exists(DOT_MING_PATH):
        models = [{"name": "huihui_ai/qwen3-abliterated:1.7b", "url": "http://localhost:11434/v1"}]
        config = {
            "num_predict": 8192,
            "num_ctx": 16384,
            "temperature": 0.8,
            "top_p": 0.9,
            "top_k": 50,
            "repeat_penalty": 1.5,
            "presence_penalty": 0.6,
            "frequency_penalty": 0.5
        }
        MOK_CONFIG = {}
        return config, models
    with open(DOT_MING_PATH, 'r', encoding='utf-8') as f:
        content = f.read()
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if '=' in line:
            key, val = line.split('=', 1)
            key = key.strip()
            val = val.strip()
            if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                val = val[1:-1]
            config[key] = val
    name_pattern = re.compile(r'^MOK_MODEL_NAME(\d*)$')
    url_pattern = re.compile(r'^MOK_MODEL_url(\d*)$')
    name_dict = {}
    url_dict = {}
    for key, val in config.items():
        m_name = name_pattern.match(key)
        if m_name:
            suffix = m_name.group(1) or "0"
            name_dict[suffix] = val
        m_url = url_pattern.match(key)
        if m_url:
            suffix = m_url.group(1) or "0"
            url_dict[suffix] = val
    all_suffixes = set(name_dict.keys()) | set(url_dict.keys())
    for suffix in all_suffixes:
        name = name_dict.get(suffix)
        url = url_dict.get(suffix)
        if name and url:
            models.append({"name": name, "url": url})
    if not models:
        models = [{"name": "huihui_ai/qwen3-abliterated:1.7b", "url": "http://localhost:11434/v1"}]
    ollama_options = {
        "num_predict": int(config.get("MOK_num_predict", 8192)),
        "num_ctx": int(config.get("MOK_num_ctx", 16384)),
        "temperature": float(config.get("MOK_temperature", 0.8)),
        "top_p": float(config.get("MOK_top_p", 0.9)),
        "top_k": int(config.get("MOK_top_k", 50)),
        "repeat_penalty": float(config.get("MOK_repeat_penalty", 1.5)),
        "presence_penalty": float(config.get("MOK_presence_penalty", 0.6)),
        "frequency_penalty": float(config.get("MOK_frequency_penalty", 0.5))
    }
    if "MOK_num_threads" in config:
        ollama_options["num_threads"] = int(config["MOK_num_threads"])
    MOK_CONFIG = {k: v for k, v in config.items() if k.startswith('MOK_')}
    return ollama_options, models

OLLAMA_OPTIONS, AVAILABLE_MODELS = parse_dot_ming()
CURRENT_MODEL_INDEX = 0
os.environ['MOK_ADMIN_CHAT_ID'] = MOK_CONFIG.get('MOK_ADMIN_CHAT_ID', '')
#print2(f"設置 MOK_ADMIN_CHAT_ID = {os.environ['MOK_ADMIN_CHAT_ID']}")

def get_current_model_config():
    return AVAILABLE_MODELS[CURRENT_MODEL_INDEX]

def get_env_files():
    if not os.path.exists(ENV_DIR):
        return []
    files = []
    for f in os.listdir(ENV_DIR):
        full = os.path.join(ENV_DIR, f)
        if f.startswith('.') and os.path.isfile(full):
            files.append(f)
    return files

def reload_config(env_path):
    global DOT_MING_PATH, OLLAMA_OPTIONS, AVAILABLE_MODELS, CURRENT_MODEL_INDEX, CURRENT_ENV_PATH
    DOT_MING_PATH = env_path
    CURRENT_ENV_PATH = env_path
    options, models = parse_dot_ming()
    OLLAMA_OPTIONS = options
    AVAILABLE_MODELS = models
    
    # --- 修改開始：根據配置文件中的 MOK_CURRENT_MODEL 設置索引 ---
    # 讀取配置文件，獲取 MOK_CURRENT_MODEL
    current_model_name = None
    try:
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line.startswith('MOK_CURRENT_MODEL='):
                    current_model_name = line.split('=', 1)[1].strip()
                    # 去除可能的引號
                    if (current_model_name.startswith('"') and current_model_name.endswith('"')) or \
                       (current_model_name.startswith("'") and current_model_name.endswith("'")):
                        current_model_name = current_model_name[1:-1]
                    break
    except Exception:
        pass
    
    # 查找索引
    new_index = 0
    if current_model_name:
        for i, m in enumerate(AVAILABLE_MODELS):
            if m['name'] == current_model_name:
                new_index = i
                break
    CURRENT_MODEL_INDEX = new_index
    # --- 修改結束 ---
    
    os.environ['MOK_ADMIN_CHAT_ID'] = MOK_CONFIG.get('MOK_ADMIN_CHAT_ID', '')
    # 同步 mokagi 配置
    mokagi.MOK_MODEL_NAME = get_current_model_config()['name']
    mokagi.OLLAMA_API = get_current_model_config()['url']
    mokagi.OLLAMA_OPTIONS.update(OLLAMA_OPTIONS)
    agent_name = os.path.basename(env_path).lstrip('.')
    os.environ['AD_MOK_AGENT_NAME'] = agent_name
    mokagi.MOK_AGENT_NAME = agent_name
    mokagi._agent_config = mokagi.load_agent_config(agent_name)

    # 重新加載所有工具模塊，使其基於新的 Agent 配置重新初始化
    tool_handler.load_tools()
    # 額外清理 memory 模塊的 chromadb 客戶端（確保重新連接）
    memory_mod = tool_handler.get_tools().get("memory")
    if memory_mod and hasattr(memory_mod, '_client'):
        memory_mod._client = None
        memory_mod._collection = None
        memory_mod._kb_collection = None

# ---------- SocketIO 聊天（核心）----------
# 在 mok_web.py 文件開頭添加（或從環境變量獲取）
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID", "none")
@socketio.on('chat_message')
def handle_chat_message(data):
    user_msg = data.get('message', '').strip()
    agent_name = data.get('agent', '')   # 從前端接收當前 agent
    if not user_msg:
        return
    #user_id = request.sid
    user_id = ADMIN_CHAT_ID

    # 累加器
    accumulated_think = ""
    accumulated_reply = ""

    async def stream_callback(event):
        nonlocal accumulated_think, accumulated_reply
        if event["type"] == "think":
            accumulated_think += event["content"]
        elif event["type"] == "reply":
            accumulated_reply += event["content"]
        elif event["type"] == "done":
            # 後端保存完整的助手回覆（防止前端斷開）
            if accumulated_reply and agent_name:
                _save_assistant_message(agent_name, accumulated_reply, accumulated_think)
        # 始終轉發給前端（若前端在線，正常顯示）
        socketio.emit('chat_stream', event, room=request.sid)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(
            process_message(user_id=user_id, text=user_msg, stream_callback=stream_callback)
        )
    except Exception as e:
        socketio.emit('chat_stream', {'type': 'reply', 'content': f"❌ 處理出錯: {str(e)}"}, room=request.sid)
        socketio.emit('chat_stream', {'type': 'done'}, room=request.sid)
    finally:
        loop.close()


def _save_assistant_message(agent, content, think_content):
    """保存助手回覆到數據庫（同步，避免阻塞）"""
    import time
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.execute(
            'INSERT INTO chat_history (agent, role, content, think_content, timestamp) VALUES (?, ?, ?, ?, ?)',
            (agent, 'assistant', content, think_content, time.time())
        )
        conn.commit()


@socketio.on('stop_generation')
def handle_stop():
    sid = request.sid
    import subprocess
    # 先通知前端服務即將重啟（可選）
    socketio.emit('stream_stopped', {'status': 'restarting'}, room=sid)
    # 立即執行 pm2 restart（不等待，後臺運行）
    subprocess.Popen("pm2 restart mok_agi", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"立即停止所有服務及緊急重啟，發起者: {sid}")

# ---------- 網頁路由（保持不變）----------
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/ASCII.html')
def ASCII():
    return render_template('ASCII.html')

@app.route('/monitor')
def monitor():
    return render_template('monitor.html')

@app.route('/api/tree')
def api_tree():
    return {'tree': get_file_tree(WATCH_PATH)}

@app.route('/api/file/<path:sub_path>')
def get_file_content(sub_path):
    if not sub_path.startswith(ALLOWED_PATHS):
        return {"error": "Unauthorized access"}, 403
    full_path = os.path.join(WATCH_PATH, sub_path)
    if not os.path.exists(full_path) or os.path.isdir(full_path):
        return {"error": "File not found"}, 404
    try:
        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return {"content": content}
    except Exception as e:
        return {"error": str(e)}, 500

@app.route('/api/raw/<path:sub_path>')
def send_raw_file(sub_path):
    if not sub_path.startswith(ALLOWED_PATHS):
        return "Unauthorized", 403
    directory = os.path.join(WATCH_PATH, os.path.dirname(sub_path))
    filename = os.path.basename(sub_path)
    return send_from_directory(directory, filename)

@app.route('/api/env_files')
def get_env_files_api():
    files = get_env_files()
    current = os.path.basename(CURRENT_ENV_PATH) if CURRENT_ENV_PATH else ""
    # 為每個 agent 獲取圖標
    agents = []
    for f in files:
        agent_name = f.lstrip('.')
        icon = '🌸'  # 默認
        config_path = os.path.join(ENV_DIR, f)
        try:
            with open(config_path, 'r', encoding='utf-8') as cf:
                for line in cf:
                    line = line.strip()
                    if line.startswith('MOK_AGENT_ICON='):
                        val = line.split('=', 1)[1].strip()
                        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                            val = val[1:-1]
                        icon = val
                        break
        except:
            pass
        agents.append({"name": agent_name, "file": f, "icon": icon})
    return {"agents": agents, "current": current}

@app.route('/api/set_env', methods=['POST'])
def set_env():
    data = request.get_json()
    filename = data.get('filename')
    if not filename:
        return {"status": "error", "message": "Missing filename"}, 400
    new_path = os.path.join(ENV_DIR, filename)
    if not os.path.exists(new_path):
        return {"status": "error", "message": "File not found"}, 404
    reload_config(new_path)
    return {"status": "ok", "current": filename, "models": AVAILABLE_MODELS, "options": OLLAMA_OPTIONS}

@app.route('/api/mok_config')
def get_mok_config():
    return MOK_CONFIG

@app.route('/api/models')
def get_models():
    return {"models": AVAILABLE_MODELS, "current_index": CURRENT_MODEL_INDEX}




@app.route('/api/set_model', methods=['POST'])
def set_model():
    global CURRENT_MODEL_INDEX
    data = request.get_json()
    model_name = None
    idx = None
    
    if 'index' in data:
        idx = int(data['index'])
        if 0 <= idx < len(AVAILABLE_MODELS):
            model_name = AVAILABLE_MODELS[idx]['name']
    elif 'name' in data:
        model_name = data['name']
        # 查找索引
        for i, m in enumerate(AVAILABLE_MODELS):
            if m['name'] == model_name:
                idx = i
                break
    
    if not model_name or idx is None:
        return {"status": "error", "message": "Invalid model"}, 400
    
    # 調用 admin 插件的 set_model_in_config 函數
    admin_mod = tool_handler.get_tools().get("admin")
    if not admin_mod or not hasattr(admin_mod, "set_model_in_config"):
        return {"status": "error", "message": "Admin module not loaded"}, 500
    
    result_message = admin_mod.set_model_in_config(model_name)
    
    # 如果成功（消息以 ✅ 開頭），則更新內存中的當前模型索引
    if result_message.startswith("✅"):
        CURRENT_MODEL_INDEX = idx
        # 同步 mokagi 配置
        mokagi.MOK_MODEL_NAME = model_name
        mokagi.OLLAMA_API = AVAILABLE_MODELS[idx]['url']
    
        # 新增：異步重啟統一進程（2 秒後重啟，讓當前請求先返回）
        import subprocess
        subprocess.Popen(
            "(sleep 2 && pm2 restart mok_agi) > /dev/null 2>&1 &",
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    return {"status": "ok" if result_message.startswith("✅") else "error", "message": result_message, "model": {"name": model_name}}










@app.route('/api/current_model')
def get_current_model():
    config = get_current_model_config()
    return {"model": config['name']}

@app.route('/api/tools')
def get_tools():
    """返回所有已加載的工具列表（用於前端展示）"""
    tools_list = []
    for mod in tool_handler.get_tools().values():
        if hasattr(mod, "PLUGIN_INFO"):
            info = mod.PLUGIN_INFO
            tools_list.append({
                "command": info.get("command", ""),
                "description": info.get("description", ""),
                "icon": info.get("icon", "🔧")
            })
    # 按命令名稱排序
    tools_list.sort(key=lambda x: x["command"])
    return {"tools": tools_list}

# ---------- 系統監控 API（保持不變）----------
@app.route('/api/system/cpu')
def system_cpu():
    import subprocess
    try:
        result = subprocess.run(
            "grep 'cpu ' /proc/stat | awk '{print ($2+$4)*100/($2+$4+$5)}'",
            shell=True, capture_output=True, text=True, timeout=5
        )
        cpu_percent = float(result.stdout.strip()) if result.stdout else 0.0
        return {"success": True, "percent": round(cpu_percent, 1)}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.route('/api/system/top')
def system_top():
    import subprocess
    try:
        result = subprocess.run("top -bn1 -o %CPU", shell=True, capture_output=True, text=True, timeout=10)
        lines = result.stdout.splitlines()
        header = lines[:5] if len(lines) >= 5 else lines
        process_lines = [line for line in lines[5:] if line.strip()]
        return {"success": True, "header": header, "processes": process_lines[:20]}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.route('/api/system/meminfo')
def system_meminfo():
    import subprocess
    try:
        result = subprocess.run("cat /proc/meminfo", shell=True, capture_output=True, text=True, timeout=5)
        if result.returncode != 0:
            return {"success": False, "error": "無法讀取內存信息"}
        meminfo = {}
        for line in result.stdout.splitlines():
            if not line.strip():
                continue
            parts = line.split(':')
            if len(parts) == 2:
                key = parts[0].strip()
                value = parts[1].strip().split()[0]
                if value.isdigit():
                    meminfo[key] = int(value)
        mem_total = meminfo.get('MemTotal', 0)
        mem_free = meminfo.get('MemFree', 0)
        mem_available = meminfo.get('MemAvailable', 0)
        buffers = meminfo.get('Buffers', 0)
        cached = meminfo.get('Cached', 0)
        swap_total = meminfo.get('SwapTotal', 0)
        swap_free = meminfo.get('SwapFree', 0)
        def to_mb(kb): return round(kb / 1024, 1)
        return {
            "success": True,
            "total_mb": to_mb(mem_total),
            "used_mb": to_mb(mem_total - mem_free - buffers - cached),
            "buffers_mb": to_mb(buffers),
            "cached_mb": to_mb(cached),
            "free_mb": to_mb(mem_free),
            "available_mb": to_mb(mem_available),
            "swap_total_mb": to_mb(swap_total),
            "swap_used_mb": to_mb(swap_total - swap_free) if swap_total > 0 else 0
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

# ---------- 聊天曆史 API（供前端展示，不使用 mokagi 的歷史）----------
@app.route('/api/chat_history', methods=['GET'])
def get_chat_history():
    agent = request.args.get('agent', '')
    if not agent:
        return {"error": "Missing agent parameter"}, 400
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            'SELECT role, content, think_content, timestamp FROM chat_history WHERE agent = ? ORDER BY id ASC',
            (agent,)
        ).fetchall()
        messages = [{
            "role": row["role"],
            "content": row["content"],
            "thinkContent": row["think_content"],
            "timestamp": row["timestamp"]
        } for row in rows]
    return {"messages": messages}

@app.route('/api/chat_history', methods=['POST'])
def post_chat_history():
    data = request.get_json()
    agent = data.get('agent')
    role = data.get('role')
    content = data.get('content')
    think_content = data.get('thinkContent')
    timestamp = data.get('timestamp', time.time())
    if not agent or not role:
        return {"error": "Missing required fields"}, 400
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.execute(
            'INSERT INTO chat_history (agent, role, content, think_content, timestamp) VALUES (?, ?, ?, ?, ?)',
            (agent, role, content, think_content, timestamp)
        )
        conn.commit()
    return {"status": "ok"}

@app.route('/api/chat_history', methods=['DELETE'])
def delete_chat_history():
    agent = request.args.get('agent', '')
    if not agent:
        return {"error": "Missing agent parameter"}, 400
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.execute('DELETE FROM chat_history WHERE agent = ?', (agent,))
        conn.commit()
    # 同時清除 mokagi 內存中的歷史
    clear_history(agent)
    return {"status": "ok"}

# ---------- 文件監控（保持不變）----------
def start_observer():
    event_handler = FileChangeHandler(socketio)
    observer = Observer()
    for item in ALLOWED_PATHS:
        target = os.path.join(WATCH_PATH, item)
        if os.path.exists(target):
            observer.schedule(event_handler, target, recursive=os.path.isdir(target))
    observer.start()
    observer.join()

# ---------- 啟動 ----------
if __name__ == '__main__':
    # 同步初始配置到 mokagi
    reload_config(CURRENT_ENV_PATH)  # 確保 mokagi 配置與網頁一致
    threading.Thread(target=start_observer, daemon=True).start()
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)