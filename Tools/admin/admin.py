PLUGIN_INFO = {
    "command": "/admin",  # 這個命令會出現在 TG 菜單
    "icon":"🤖",
    "handler": "handle_admin",
    "description": "管理工具 (htop, ollama list, rm 等)",
    "intent_keywords": [
        ("系統負載", "/admin htop"),
        ("htop", "/admin htop"),
        ("查看負載", "/admin htop"),
        ("CPU使用率", "/admin cpu"),
        ("cpu", "/admin cpu"),
        ("查看cpu", "/admin cpu"),
        ("模型列表", "/admin ollama_list"),
        ("已安裝模型", "/admin ollama_list"),
        ("ollama列表", "/admin ollama_list"),
        ("刪除模型", "/admin ollama_rm"),
        ("移除模型", "/admin ollama_rm"),
        ("日誌", "/admin logs"),
        ("查看日誌", "/admin logs"),
        ("pm2日誌", "/admin logs")
    ],
    "updata":"202604301052"
}

import os
import subprocess
import logging

# 從環境變量獲取管理員 ID，用於敏感操作權限檢查
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID", "")

def is_admin(chat_id: str) -> bool:
    """判斷當前用戶是否為管理員"""
    return str(chat_id) == ADMIN_CHAT_ID

def is_model_running(model_name: str) -> bool:
    """檢查模型是否正在被 Ollama 使用"""
    try:
        result = subprocess.run(
            "ollama ps", shell=True,
            capture_output=True, text=True, timeout=10
        )
        # 提取運行的模型名稱（格式：NAME      ID    SIZE    PROCESSOR    UNTIL）
        lines = result.stdout.strip().split('\n')[1:]  # 跳過表頭
        for line in lines:
            parts = line.split()
            if parts and parts[0] == model_name:
                return True
        return False
    except Exception:
        return False  # 如果檢查出錯，為安全起見默認認為不在運行，但可以記錄日誌

def handle_admin(args: str, chat_id: str = None) -> str:
    """
    管理命令路由，根據 args 執行不同操作
    用法示例：
        /admin htop
        /admin ollama_list
        /admin ollama_rm mok_3b:latest
    """
    logging.info(f"Admin plugin invoked: args='{args}', chat_id={chat_id}")
    args = args.strip()
    if not args:
        return "可用管理命令：\n" \
               "  /admin htop        - 查看系統負載\n" \
               "  /admin cpu          - 查看 CPU 使用率\n" \
               "  /admin ollama_list  - 查看已安裝的模型\n" \
               "  /admin ollama_rm <模型名> - 刪除指定模型\n" \
               "  /admin logs <行數>  - 查看 MokAgi 日誌 (預設15行)"

    # --- 公開命令（任何授權用戶都可執行）---
    if args == "htop":
        try:
            result = subprocess.run(
                "top -bn1 | head -n 5", shell=True,
                capture_output=True, text=True, timeout=10
            )
            return f"<pre>{result.stdout}</pre>" if result.stdout else "無法獲取系統負載。"
        except Exception as e:
            return f"❌ 執行失敗: {e}"

    elif args == "cpu":
        try:
            result = subprocess.run(
                "grep 'cpu ' /proc/stat | awk '{print \"CPU使用率: \" ($2+$4)*100/($2+$4+$5) \"%\"}'", 
                shell=True, capture_output=True, text=True, timeout=10
            )
            return f"🖥 {result.stdout.strip()}"
        except Exception as e:
            return f"❌ 執行失敗: {e}"

    elif args == "ollama_list":
        try:
            result = subprocess.run(
                "ollama list", shell=True,
                capture_output=True, text=True, timeout=30
            )
            return f"<pre>{result.stdout}</pre>" if result.stdout else "沒有安裝任何模型。"
        except Exception as e:
            return f"❌ 執行失敗: {e}"

    elif args.startswith("logs"):
        # 默認顯示 15 行，可指定 /admin logs 30
        lines = args.split()
        num = lines[1] if len(lines) > 1 and lines[1].isdigit() else 15
        try:
            result = subprocess.run(
                f"pm2 logs MokAgi --lines {num} --nostream --raw", shell=True,
                capture_output=True, text=True, timeout=30
            )
            return f"<pre>{result.stdout[-4000:]}</pre>" if result.stdout else "沒有日誌。"
        except Exception as e:
            return f"❌ 執行失敗: {e}"

    # --- 敏感命令（僅管理員）---
    elif args.startswith("ollama_rm"):
        if not chat_id or not is_admin(chat_id):
            return "⛔ 此操作僅限管理員執行。"

        parts = args.split()
        if len(parts) < 2:
            return "用法: /admin ollama_rm <模型名稱>"

        model_name = parts[1]

        # 檢查模型是否正在運行
        if is_model_running(model_name):
            return f"⛔ 錯誤：模型 {model_name} 正在使用中，無法刪除。請先停止所有使用該模型的應用。"

        try:
            result = subprocess.run(
                f"ollama rm {model_name}", shell=True,
                capture_output=True, text=True, timeout=60
            )
            if result.returncode == 0:
                return f"✅ 模型 {model_name} 已刪除。"
            else:
                return f"❌ 刪除失敗: {result.stderr}"
        except Exception as e:
            return f"❌ 執行失敗: {e}"

    else:
        return f"未知管理命令: {args}\n發送 /admin 查看可用命令。"