"""
mok_web.py
網頁前端適配器（基於 mokagi）
提供文件瀏覽器、系統監控、聊天界面，所有 AI 對話能力調用 mokagi 模塊。
202605170422
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
            print(f"File modified: {rel_path}")
            self.socketio.emit('file_change', {'path': rel_path})

def get_file_tree(path):
    tree = []
    try:
        current_path = os.path.normpath(path)
        base_path = os.path.normpath(WATCH_PATH)
        if current_path == base_path:
            items = [item for item in ALLOWED_PATHS if os.path.exists(os.path.join(current_path, item))]
        else:
            items = sorted([f for f in os.listdir(current_path) if not f.startswith('.')])
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
        models = [{"name": "huihui_ai/qwen3-abliterated:1.7b", "url": "http://localhost:11434/api/generate"}]
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
    url_pattern = re.compile(r'^MOK_MODEL_api(\d*)$')
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
        models = [{"name": "huihui_ai/qwen3-abliterated:1.7b", "url": "http://localhost:11434/api/generate"}]
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
print(f"設置 MOK_ADMIN_CHAT_ID = {os.environ['MOK_ADMIN_CHAT_ID']}")

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
    CURRENT_MODEL_INDEX = 0
    os.environ['MOK_ADMIN_CHAT_ID'] = MOK_CONFIG.get('MOK_ADMIN_CHAT_ID', '')
    # 同步 mokagi 的配置（模型名稱、API、參數）
    mokagi.MOK_MODEL_NAME = get_current_model_config()['name']
    mokagi.OLLAMA_API = get_current_model_config()['url']
    mokagi.OLLAMA_OPTIONS.update(OLLAMA_OPTIONS)
    print(f"同步 mokagi 配置: model={mokagi.MOK_MODEL_NAME}, api={mokagi.OLLAMA_API}")

# ---------- SocketIO 聊天（核心）----------
@socketio.on('chat_message')
def handle_chat_message(data):
    user_msg = data.get('message', '').strip()
    if not user_msg:
        return

    # 使用 session id 作為 user_id（也可以使用 IP + User-Agent 組合，這裡簡單用 request.sid）
    user_id = request.sid

    # 定義流式回調函數，將 mokagi 的事件轉發到前端
    async def stream_callback(event):
        # event 格式: {"type": "think"|"reply"|"done", "content": str}
        socketio.emit('chat_stream', event, room=request.sid)

    # 在新的事件循環中運行異步處理
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

@socketio.on('stop_generation')
def handle_stop():
    # 停止生成（需要 mokagi 支持中斷，當前版本未實現，保留接口）
    sid = request.sid
    socketio.emit('stream_stopped', room=sid)
    print(f"Stopped generation for {sid}")

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
    return {"files": files, "current": current}

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
    if 'index' in data:
        idx = int(data['index'])
        if 0 <= idx < len(AVAILABLE_MODELS):
            CURRENT_MODEL_INDEX = idx
            # 同步 mokagi 配置
            mokagi.MOK_MODEL_NAME = AVAILABLE_MODELS[idx]['name']
            mokagi.OLLAMA_API = AVAILABLE_MODELS[idx]['url']
            return {"status": "ok", "model": AVAILABLE_MODELS[idx]}
    elif 'name' in data:
        for i, m in enumerate(AVAILABLE_MODELS):
            if m['name'] == data['name']:
                CURRENT_MODEL_INDEX = i
                mokagi.MOK_MODEL_NAME = m['name']
                mokagi.OLLAMA_API = m['url']
                return {"status": "ok", "model": m}
    return {"status": "error", "message": "Invalid model"}, 400

@app.route('/api/current_model')
def get_current_model():
    config = get_current_model_config()
    return {"model": config['name']}

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