#!/usr/bin/env python3


"""
202605250320
launcher.py - 統一啟動 pm2 24小時運行的多個 agent 和網頁界面，支持 source 配置文件加載環境變量
- 從 ~/.mok/ 目錄下讀取以 . 開頭的配置文件
"""


import os
import sys
import subprocess
import threading
import queue
import time
import signal
from pathlib import Path

PROJECT_DIR = Path.home() / ".mok"
EXCLUDE_FILES = {".env"}
processes = []
stop_event = threading.Event()

def log_with_prefix(prefix, line):
    line = line.rstrip('\n')
    print(f"{prefix} {line}", flush=True)

def stream_reader(pipe, prefix, output_queue):
    for line in iter(pipe.readline, ''):
        if not line:
            break
        output_queue.put((prefix, line))

def get_env_from_config(config_path):
    """通過 bash source 配置文件獲取環境變量字典"""
    # 使用 bash 執行 source，然後打印所有變量
    script = f"""
source "{config_path}"
env | grep -E '^(MOK_|TAVILY_)'  # 只導出 MOK_ 和 TAVILY_ 相關變量
"""
    try:
        output = subprocess.check_output(['bash', '-c', script], text=True)
        env = {}
        for line in output.strip().split('\n'):
            if '=' in line:
                k, v = line.split('=', 1)
                env[k] = v
        return env
    except Exception as e:
        log_with_prefix("[Launcher]", f"加載配置失敗 {config_path}: {e}")
        return {}

def start_bot(agent_name, config_path):
    env = os.environ.copy()
    env.update(get_env_from_config(config_path))
    env["MOK_AGENT_NAME"] = agent_name
    env["MOKAGI_HOME"] = "mok"
    env["PYTHONPATH"] = str(PROJECT_DIR)

    bot_script = PROJECT_DIR / "frontends" / "mok_tg.py"
    if not bot_script.exists():
        log_with_prefix(f"[Bot:{agent_name}]", f"錯誤: {bot_script} 不存在")
        return None

    proc = subprocess.Popen(
        [sys.executable, str(bot_script)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env=env, cwd=str(PROJECT_DIR), text=True, bufsize=1
    )
    return proc

def start_web(port=5000):
    env = os.environ.copy()
    # 網頁界面不需要特定 agent 配置，但可以加載默認配置作為 fallback
    default_cfg = PROJECT_DIR / ".default"
    if default_cfg.exists():
        env.update(get_env_from_config(default_cfg))
    env["MOKAGI_HOME"] = "mok"
    env["PYTHONPATH"] = str(PROJECT_DIR)

    web_script = PROJECT_DIR / "frontends" / "mok_web.py"
    if not web_script.exists():
        log_with_prefix("[Web]", f"錯誤: {web_script} 不存在")
        return None

    proc = subprocess.Popen(
        [sys.executable, str(web_script), "--port", str(port)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env=env, cwd=str(PROJECT_DIR), text=True, bufsize=1
    )
    return proc

def signal_handler(sig, frame):
    print("\n收到退出信號，關閉所有子進程...", flush=True)
    stop_event.set()
    for p in processes:
        if p and p.poll() is None:
            p.terminate()
    time.sleep(1)
    for p in processes:
        if p and p.poll() is None:
            p.kill()
    sys.exit(0)

def main():
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    print("MOK AGI 統一啟動器 (source 方式加載配置)", flush=True)
    print(f"項目目錄: {PROJECT_DIR}", flush=True)

    config_files = []
    for item in PROJECT_DIR.iterdir():
        if item.is_file() and item.name.startswith('.') and item.name not in EXCLUDE_FILES:
            config_files.append((item.name[1:], item))
            print(f"發現配置: {item.name[1:]} -> {item.name}", flush=True)

    output_queue = queue.Queue()

    for agent_name, cfg_path in config_files:
        print(f"正在啟動機器人: {agent_name}", flush=True)
        proc = start_bot(agent_name, cfg_path)
        if proc:
            processes.append(proc)
            threading.Thread(target=stream_reader, args=(proc.stdout, f"[Bot:{agent_name}]", output_queue), daemon=True).start()
            threading.Thread(target=stream_reader, args=(proc.stderr, f"[Bot:{agent_name}][ERR]", output_queue), daemon=True).start()
        else:
            print(f"啟動機器人 {agent_name} 失敗", flush=True)

    print("正在啟動網頁界面...", flush=True)
    web_proc = start_web(5000)
    if web_proc:
        processes.append(web_proc)
        threading.Thread(target=stream_reader, args=(web_proc.stdout, "[Web]", output_queue), daemon=True).start()
        threading.Thread(target=stream_reader, args=(web_proc.stderr, "[Web][ERR]", output_queue), daemon=True).start()

    print(f"已啟動 {len(processes)} 個服務（{len(config_files)} 個機器人 + 1 個網頁）", flush=True)

    def handle_output():
        while not stop_event.is_set():
            try:
                prefix, line = output_queue.get(timeout=0.5)
                log_with_prefix(prefix, line)
            except queue.Empty:
                continue
    threading.Thread(target=handle_output, daemon=True).start()

    while not stop_event.is_set():
        if any(p.poll() is not None for p in processes):
            print("有服務意外退出，5秒後自動重啟所有服務...", flush=True)
            time.sleep(5)
            signal_handler(None, None)
        time.sleep(2)

if __name__ == "__main__":
    main()