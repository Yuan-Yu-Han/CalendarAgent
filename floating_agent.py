#!/usr/bin/env python3
"""
floating_agent.py

FloatingDialog — macOS/iOS 风格浮动日历助手（使用 OpenAI API）
  • 作为库供 service.py 调用（持久后台模式）
  • 单独运行：python floating_agent.py（读取剪贴板，一次性）
"""

import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from datetime import datetime

# 加载项目目录下的 .env 文件
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip().strip("'\""))

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from openai import OpenAI
except ImportError:
    print("缺少依赖：pip install openai")
    sys.exit(1)

from calendar_tools import (
    create_calendar_event,
    create_reminder,
    list_calendars,
    list_reminder_lists,
)

# ── 配置 ──────────────────────────────────────────────────────────────────────

MODEL  = os.environ.get("CALENDAR_AGENT_MODEL", "gpt-4o-mini")
WIN_W  = 420
WIN_H  = 560
RADIUS = 16   # 圆角半径（px）
PAD    = RADIUS  # 内容区域距窗口边缘

# macOS / iOS 系统色（浅色模式）
C = {
    "bg":        "#F2F2F7",   # systemGroupedBackground
    "surface":   "#FFFFFF",   # systemBackground
    "overlay":   "#C6C6C8",   # separator
    "separator": "#C6C6C8",
    "text":      "#1C1C1E",   # label
    "label2":    "#6C6C70",   # secondaryLabel
    "blue":      "#007AFF",   # systemBlue
    "green":     "#34C759",   # systemGreen
    "red":       "#FF3B30",   # systemRed
    "orange":    "#FF9500",   # systemOrange
    "teal":      "#32ADE6",   # systemTeal
}

# ── 辅助函数 ──────────────────────────────────────────────────────────────────

def get_clipboard() -> str:
    return subprocess.run(["pbpaste"], capture_output=True, text=True).stdout.strip()

def get_cursor_position():
    try:
        from pynput.mouse import Controller
        return Controller().position
    except Exception:
        return None

def smart_pos(cursor, sw: int, sh: int) -> tuple[int, int]:
    if cursor:
        x = int(min(cursor[0] + 24, sw - WIN_W - 20))
        y = int(min(max(cursor[1] - WIN_H // 3, 20), sh - WIN_H - 40))
    else:
        x = sw - WIN_W - 30
        y = max((sh - WIN_H) // 4, 20)
    return x, y

def _rrect_points(x1, y1, x2, y2, r):
    """生成圆角矩形的多边形控制点（配合 smooth=True 使用）。"""
    return [
        x1+r, y1,   x2-r, y1,
        x2,   y1,   x2,   y1+r,
        x2,   y2-r, x2,   y2,
        x2-r, y2,   x1+r, y2,
        x1,   y2,   x1,   y2-r,
        x1,   y1+r, x1,   y1,
    ]

# ── FloatingDialog ─────────────────────────────────────────────────────────────

class FloatingDialog:
    """
    macOS/iOS 风格浮动对话框。
    始终作为已有 tk.Tk root 的 Toplevel 子窗口创建。
    mainloop 由调用方（service.py 或 standalone main()）负责。
    """

    def __init__(self, parent: tk.Tk, text: str, cursor_pos=None):
        self.parent     = parent
        self.text       = text
        self.cursor_pos = cursor_pos
        self.ui_queue   = queue.Queue()
        self.client     = OpenAI()

        self.window = tk.Toplevel(parent)
        self._build_window()
        self._build_ui()

    # ── 窗口 ──────────────────────────────────────────────────────────────────

    def _build_window(self):
        w = self.window
        w.title("")
        w.overrideredirect(True)
        w.attributes("-topmost", True)

        # macOS 透明背景 → 实现真正圆角
        self._transparent = False
        try:
            w.attributes("-transparent", True)
            w.configure(bg="systemTransparent")
            self._transparent = True
        except Exception:
            w.configure(bg=C["bg"])
            w.attributes("-alpha", 0.97)

        sw = w.winfo_screenwidth()
        sh = w.winfo_screenheight()
        x, y = smart_pos(self.cursor_pos, sw, sh)
        w.geometry(f"{WIN_W}x{WIN_H}+{x}+{y}")
        self._dx = self._dy = 0

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        w = self.window
        cv_bg = "systemTransparent" if self._transparent else C["bg"]

        # Canvas：绘制圆角矩形背景
        self._cv = tk.Canvas(w, width=WIN_W, height=WIN_H,
                              highlightthickness=0, bg=cv_bg)
        self._cv.place(x=0, y=0)

        pts = _rrect_points(0, 0, WIN_W, WIN_H, RADIUS)
        self._cv.create_polygon(pts, smooth=True,
                                 fill=C["bg"], outline=C["overlay"], width=1)

        # 内容框架（内缩 PAD 像素，确保完全在圆角矩形内）
        content = tk.Frame(w, bg=C["bg"])
        content.place(x=PAD, y=PAD,
                      width=WIN_W - PAD * 2,
                      height=WIN_H - PAD * 2)
        self._build_content(content)

    def _build_content(self, p):
        INNER_W = WIN_W - PAD * 2   # 内容区有效宽度

        # ── 标题栏 ────────────────────────────────────────────────────────────
        hdr = tk.Frame(p, bg=C["bg"])
        hdr.pack(fill=tk.X)

        icon = tk.Label(hdr, text="📅", bg=C["bg"],
                        font=("Helvetica Neue", 16))
        icon.pack(side=tk.LEFT)

        title = tk.Label(hdr, text="  Calendar Agent",
                         bg=C["bg"], fg=C["text"],
                         font=("Helvetica Neue", 15, "bold"))
        title.pack(side=tk.LEFT)

        close = tk.Label(hdr, text="✕",
                         bg=C["bg"], fg=C["label2"],
                         font=("Helvetica Neue", 17),
                         cursor="hand2", padx=4)
        close.pack(side=tk.RIGHT)
        close.bind("<Button-1>", lambda e: self.window.destroy())
        close.bind("<Enter>",    lambda e: close.config(fg=C["red"]))
        close.bind("<Leave>",    lambda e: close.config(fg=C["label2"]))

        for widget in (hdr, icon, title):
            widget.bind("<ButtonPress-1>", self._drag_start)
            widget.bind("<B1-Motion>",     self._drag_move)

        # ── 分隔线 ────────────────────────────────────────────────────────────
        tk.Frame(p, bg=C["separator"], height=1).pack(fill=tk.X, pady=(10, 8))

        # ── 框选内容预览 ──────────────────────────────────────────────────────
        tk.Label(p, text="框选内容",
                 bg=C["bg"], fg=C["label2"],
                 font=("Helvetica Neue", 12)).pack(anchor=tk.W, pady=(0, 4))

        preview_box = tk.Frame(p, bg=C["surface"],
                               highlightbackground=C["overlay"],
                               highlightthickness=1)
        preview_box.pack(fill=tk.X)

        preview_text = self.text[:220] + ("…" if len(self.text) > 220 else "")
        tk.Label(preview_box, text=preview_text,
                 bg=C["surface"], fg=C["text"],
                 font=("Helvetica Neue", 12),
                 wraplength=INNER_W - 24,
                 justify=tk.LEFT,
                 padx=10, pady=8).pack(anchor=tk.W)

        # ── 分隔线 ────────────────────────────────────────────────────────────
        tk.Frame(p, bg=C["separator"], height=1).pack(fill=tk.X, pady=(10, 8))

        # ── AI 分析输出区 ─────────────────────────────────────────────────────
        tk.Label(p, text="AI 分析",
                 bg=C["bg"], fg=C["label2"],
                 font=("Helvetica Neue", 12)).pack(anchor=tk.W, pady=(0, 4))

        txt_box = tk.Frame(p, bg=C["surface"],
                           highlightbackground=C["overlay"],
                           highlightthickness=1)
        txt_box.pack(fill=tk.BOTH, expand=True)

        self.txt = tk.Text(txt_box,
                           bg=C["surface"], fg=C["text"],
                           font=("Menlo", 11),
                           wrap=tk.WORD, bd=0,
                           padx=10, pady=8,
                           state=tk.DISABLED, cursor="arrow")
        sb = tk.Scrollbar(txt_box, orient=tk.VERTICAL,
                          command=self.txt.yview, width=8)
        self.txt.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.txt.pack(fill=tk.BOTH, expand=True)

        self.txt.tag_configure("normal",    foreground=C["text"])
        self.txt.tag_configure("tool_name", foreground=C["blue"],
                               font=("Menlo", 11, "bold"))
        self.txt.tag_configure("tool_args", foreground=C["label2"])
        self.txt.tag_configure("ok",        foreground=C["green"])
        self.txt.tag_configure("err",       foreground=C["red"])
        self.txt.tag_configure("done",      foreground=C["teal"],
                               font=("Menlo", 11, "bold"))

        # ── 状态栏 ────────────────────────────────────────────────────────────
        tk.Frame(p, bg=C["separator"], height=1).pack(fill=tk.X, pady=(8, 4))
        self._status_var = tk.StringVar(value="正在启动…")
        tk.Label(p, textvariable=self._status_var,
                 bg=C["bg"], fg=C["label2"],
                 font=("Helvetica Neue", 11)).pack(anchor=tk.W)

    # ── 拖拽 ──────────────────────────────────────────────────────────────────

    def _drag_start(self, e):
        self._dx, self._dy = e.x, e.y

    def _drag_move(self, e):
        x = self.window.winfo_x() + e.x - self._dx
        y = self.window.winfo_y() + e.y - self._dy
        self.window.geometry(f"+{x}+{y}")

    # ── 线程安全 UI 操作 ──────────────────────────────────────────────────────

    def _append(self, text: str, tag: str = "normal"):
        try:
            self.txt.configure(state=tk.NORMAL)
            self.txt.insert(tk.END, text, tag)
            self.txt.see(tk.END)
            self.txt.configure(state=tk.DISABLED)
        except tk.TclError:
            pass

    def _set_status(self, text: str):
        try:
            self._status_var.set(text)
        except tk.TclError:
            pass

    # ── 队列轮询（主线程）────────────────────────────────────────────────────

    def _poll(self):
        try:
            if not self.window.winfo_exists():
                return
        except tk.TclError:
            return

        try:
            while True:
                msg  = self.ui_queue.get_nowait()
                kind = msg[0]
                if kind == "text":
                    self._append(msg[1])
                elif kind == "tool_call":
                    name, args = msg[1], msg[2]
                    self._append(f"\n  🔧 {name}\n", "tool_name")
                    lines    = json.dumps(args, ensure_ascii=False, indent=2)
                    indented = "\n".join("     " + ln for ln in lines.splitlines())
                    self._append(indented + "\n", "tool_args")
                elif kind == "tool_result":
                    result, ok = msg[1], msg[2]
                    icon = "  ✅ " if ok else "  ❌ "
                    tag  = "ok"  if ok else "err"
                    self._append(f"{icon}{json.dumps(result, ensure_ascii=False)}\n", tag)
                elif kind == "status":
                    self._set_status(msg[1])
                elif kind == "done":
                    self._append("\n✨  完成！已同步到日历 / 提醒事项。\n", "done")
                    self._set_status("完成 · 按 ✕ 关闭")
                elif kind == "error":
                    self._append(f"\n❌  错误：{msg[1]}\n", "err")
                    self._set_status("出错了")
        except queue.Empty:
            pass

        self.window.after(60, self._poll)

    # ── Agent 线程（OpenAI）──────────────────────────────────────────────────

    def _agent_thread(self):
        q = self.ui_queue
        try:
            q.put(("status", "获取日历列表…"))
            calendars      = list_calendars()
            reminder_lists = list_reminder_lists()

            today     = datetime.now().strftime("%Y年%m月%d日")
            today_iso = datetime.now().strftime("%Y-%m-%d")

            system = f"""你是一个智能日历助手。今天是 {today}（ISO: {today_iso}）。

可用日历: {", ".join(calendars) if calendars else "默认日历"}
可用提醒列表: {", ".join(reminder_lists) if reminder_lists else "提醒事项"}

处理流程：
1. 阅读文本，提取事件、约会、任务、截止日期、提醒
2. 有具体时间的事件 → create_calendar_event
3. 任务 / 待办 / 无固定时间 → create_reminder
4. 智能推断相对时间（"明天"、"下周五"、"下午三点"等）
5. 完成后给出简洁中文总结

日期格式：ISO 8601 (YYYY-MM-DDTHH:MM:SS)
无结束时间时默认时长 1 小时；无具体时间的提醒默认 09:00"""

            tools = [
                {
                    "type": "function",
                    "function": {
                        "name": "create_calendar_event",
                        "description": "在 macOS Calendar.app 创建日历事件（自动同步到 iOS）",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "title":         {"type": "string"},
                                "start_date":    {"type": "string", "description": "ISO 8601"},
                                "end_date":      {"type": "string", "description": "ISO 8601"},
                                "calendar_name": {"type": "string"},
                                "notes":         {"type": "string"},
                                "location":      {"type": "string"},
                            },
                            "required": ["title", "start_date", "end_date"],
                        },
                    },
                },
                {
                    "type": "function",
                    "function": {
                        "name": "create_reminder",
                        "description": "在 macOS Reminders.app 创建提醒事项（自动同步到 iOS）",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "title":     {"type": "string"},
                                "due_date":  {"type": "string", "description": "ISO 8601，可选"},
                                "list_name": {"type": "string"},
                                "notes":     {"type": "string"},
                                "priority":  {"type": "integer",
                                              "description": "0=无 1=高 5=中 9=低"},
                            },
                            "required": ["title"],
                        },
                    },
                },
            ]

            messages = [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": (
                        "请分析以下文本，提取事件和任务，"
                        "创建相应的日历事件和提醒事项：\n\n" + self.text
                    ),
                },
            ]

            q.put(("status", "AI 正在分析…"))

            # ── Agentic loop ──────────────────────────────────────────────────
            while True:
                collected_content    = []
                collected_tool_calls = {}
                finish_reason        = None

                # 流式输出（文字实时显示，tool_call 分块组装）
                with self.client.chat.completions.create(
                    model=MODEL,
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                    stream=True,
                ) as stream:
                    for chunk in stream:
                        choice        = chunk.choices[0]
                        delta         = choice.delta
                        finish_reason = choice.finish_reason or finish_reason

                        if delta.content:
                            collected_content.append(delta.content)
                            q.put(("text", delta.content))

                        if delta.tool_calls:
                            for tc in delta.tool_calls:
                                idx = tc.index
                                if idx not in collected_tool_calls:
                                    collected_tool_calls[idx] = {
                                        "id":       tc.id or "",
                                        "type":     "function",
                                        "function": {"name": tc.function.name or "",
                                                     "arguments": ""},
                                    }
                                if tc.id:
                                    collected_tool_calls[idx]["id"] = tc.id
                                if tc.function.name:
                                    collected_tool_calls[idx]["function"]["name"] = tc.function.name
                                if tc.function.arguments:
                                    collected_tool_calls[idx]["function"]["arguments"] += tc.function.arguments

                full_content    = "".join(collected_content)
                tool_calls_list = [collected_tool_calls[i]
                                   for i in sorted(collected_tool_calls)]

                asst_msg = {"role": "assistant", "content": full_content or None}
                if tool_calls_list:
                    asst_msg["tool_calls"] = tool_calls_list
                messages.append(asst_msg)

                if finish_reason != "tool_calls":
                    break

                # ── 执行工具调用 ──────────────────────────────────────────────
                q.put(("status", "执行工具…"))
                tool_results = []

                for tc in tool_calls_list:
                    name = tc["function"]["name"]
                    args = json.loads(tc["function"]["arguments"])
                    q.put(("tool_call", name, args))
                    try:
                        if name == "create_calendar_event":
                            result = create_calendar_event(**args)
                        elif name == "create_reminder":
                            result = create_reminder(**args)
                        else:
                            result = {"error": f"未知工具: {name}"}
                        q.put(("tool_result", result, True))
                    except Exception as exc:
                        result = {"error": str(exc)}
                        q.put(("tool_result", result, False))

                    tool_results.append({
                        "role":         "tool",
                        "tool_call_id": tc["id"],
                        "content":      json.dumps(result, ensure_ascii=False),
                    })

                messages.extend(tool_results)
                q.put(("status", "AI 继续处理…"))

            q.put(("done", None))

        except Exception as exc:
            q.put(("error", str(exc)))

    # ── 启动（由 service.py 或 standalone main() 调用）────────────────────────

    def start(self):
        threading.Thread(target=self._agent_thread, daemon=True).start()
        self._poll()


# ── 单独运行入口 ──────────────────────────────────────────────────────────────

def main():
    if not os.environ.get("OPENAI_API_KEY"):
        print("❌  请在 .env 文件中设置 OPENAI_API_KEY")
        sys.exit(1)

    clipboard = get_clipboard()
    if not clipboard:
        print("📋  剪贴板为空！请先框选或复制一些文本。")
        sys.exit(0)

    root = tk.Tk()
    root.withdraw()

    dialog = FloatingDialog(root, clipboard, get_cursor_position())
    dialog.window.protocol("WM_DELETE_WINDOW", root.destroy)
    dialog.start()
    root.mainloop()


if __name__ == "__main__":
    main()
