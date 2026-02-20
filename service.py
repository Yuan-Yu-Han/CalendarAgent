#!/usr/bin/env python3
"""
service.py — 后台热键服务

用法：
  python service.py

功能：
  • 监听全局快捷键（默认 Ctrl+Shift+Space）
  • 按下快捷键时，自动模拟 Cmd+C 复制框选文字
  • 弹出 FloatingDialog 对话框进行日历事件创建

环境变量：
  OPENAI_API_KEY    必须设置（在 .env 文件中配置）
  CALENDAR_HOTKEY   快捷键，默认 <ctrl>+<shift>+<space>
                      格式参考 pynput GlobalHotKeys 文档
                      例：<cmd>+<shift>+space 或 <ctrl>+<shift>+c
"""

import os
import sys
import time
import subprocess
import threading
import tkinter as tk

# 加载项目目录下的 .env 文件
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip().strip("'\""))

# ── 依赖检查 ──────────────────────────────────────────────────────────────────

try:
    from pynput import keyboard
    from pynput.keyboard import Key, Controller as KbController
except ImportError:
    print("缺少依赖：pip install pynput")
    sys.exit(1)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from floating_agent import FloatingDialog, get_cursor_position
except ImportError as e:
    print(f"导入 floating_agent 失败: {e}")
    sys.exit(1)

# ── 配置 ──────────────────────────────────────────────────────────────────────

HOTKEY = os.environ.get("CALENDAR_HOTKEY", "<ctrl>+<shift>+<space>")
COPY_DELAY = 0.15   # 模拟 Cmd+C 后等待剪贴板更新的秒数（可酌情调大）

_kb = KbController()

# ── 辅助函数 ──────────────────────────────────────────────────────────────────

def simulate_copy() -> str:
    """模拟 Cmd+C，等待剪贴板更新，返回剪贴板内容。"""
    # 记录旧内容，用于判断复制是否成功
    old = subprocess.run(["pbpaste"], capture_output=True, text=True).stdout

    # 模拟 Cmd+C
    _kb.press(Key.cmd)
    _kb.press('c')
    _kb.release('c')
    _kb.release(Key.cmd)

    time.sleep(COPY_DELAY)

    new = subprocess.run(["pbpaste"], capture_output=True, text=True).stdout.strip()
    return new


def open_dialog(root: tk.Tk):
    """在主线程中弹出对话框（由 root.after 调度）。"""
    text = simulate_copy()

    if not text:
        # 没有框选文字时，给出提示
        _show_toast(root, "⚠️  未检测到框选文字，请先框选再按快捷键")
        return

    cursor = get_cursor_position()
    dialog = FloatingDialog(root, text, cursor)
    dialog.window.protocol("WM_DELETE_WINDOW", dialog.window.destroy)
    dialog.start()


def _show_toast(root: tk.Tk, msg: str):
    """短暂显示一个提示窗口。"""
    t = tk.Toplevel(root)
    t.overrideredirect(True)
    t.attributes("-topmost", True)
    t.attributes("-alpha", 0.88)
    t.configure(bg="#313244")

    sw, sh = t.winfo_screenwidth(), t.winfo_screenheight()
    w, h = 360, 48
    t.geometry(f"{w}x{h}+{(sw - w) // 2}+{sh - h - 80}")

    tk.Label(t, text=msg, bg="#313244", fg="#f9e2af",
             font=("Helvetica", 12), padx=12).pack(expand=True)

    t.after(2000, t.destroy)

# ── 主程序 ────────────────────────────────────────────────────────────────────

def main():
    if not os.environ.get("OPENAI_API_KEY"):
        print("❌  请在 .env 文件中设置 OPENAI_API_KEY")
        sys.exit(1)

    # 隐藏主窗口（只作为 Toplevel 的父容器）
    root = tk.Tk()
    root.withdraw()
    root.title("CalendarAgent Service")

    # 快捷键触发时，把 open_dialog 调度到 tkinter 主线程
    def on_hotkey():
        root.after(0, lambda: open_dialog(root))

    hotkeys = {HOTKEY: on_hotkey}

    listener = keyboard.GlobalHotKeys(hotkeys)
    listener.start()

    print(f"✅  CalendarAgent 后台服务已启动")
    print(f"   快捷键：{HOTKEY}")
    print(f"   使用方法：框选文字 → 按 {HOTKEY}")
    print(f"   按 Ctrl+C 退出服务")
    print()

    try:
        root.mainloop()
    except KeyboardInterrupt:
        pass
    finally:
        listener.stop()
        print("服务已停止。")


if __name__ == "__main__":
    main()
