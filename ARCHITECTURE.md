# CalendarAgent — 架构与执行流程说明

## 项目概览

这个项目有**两套完全独立的运行模式**，共用同一个底层工具库：

```
┌─────────────────────────────────────────────────────────┐
│                      两种入口                            │
│                                                         │
│   模式 A：MCP Server          模式 B：后台热键服务         │
│   (mcp_server.py)             (service.py)              │
│   配合 Claude Code 使用        独立运行，OpenAI 驱动       │
└────────────────┬──────────────────────┬─────────────────┘
                 │                      │
                 └──────────┬───────────┘
                            │
                 ┌──────────▼───────────┐
                 │   calendar_tools.py  │  ← 共用底层
                 │   AppleScript 调用    │
                 └──────────┬───────────┘
                            │ osascript
                 ┌──────────▼───────────┐
                 │  macOS Calendar.app  │
                 │  macOS Reminders.app │
                 └──────────┬───────────┘
                            │ iCloud 自动同步
                 ┌──────────▼───────────┐
                 │      iPhone / iPad   │
                 └──────────────────────┘
```

---

## 模式 A：MCP Server（配合 Claude Code）

### 什么是 MCP？

MCP（Model Context Protocol）是 Anthropic 定义的一套标准协议，让 AI 模型可以安全地调用外部工具。Claude Code（命令行工具）支持 MCP，可以把你本地的脚本注册成工具，供 Claude 直接调用。

**关键点：这个模式用的是你的 Claude Pro/Claude Code 订阅，不需要额外的 API Key。**

### 注册方式

```bash
claude mcp add calendar-agent python /Users/yuany/CalendarAgent/mcp_server.py
```

### 执行流程

```
你在 Claude Code 里输入指令
        │
        ▼
Claude Code（CLI）判断需要调用日历工具
        │
        │  stdio（标准输入输出）
        ▼
mcp_server.py 收到请求
  ├─ get_clipboard      → 读取系统剪贴板（pbpaste）
  ├─ list_calendars     → 查询日历列表
  ├─ list_reminder_lists→ 查询提醒列表
  ├─ create_calendar_event → 创建日历事件
  └─ create_reminder    → 创建提醒事项
        │
        ▼
calendar_tools.py
  └─ run_applescript() → 调用 osascript 执行 AppleScript
        │
        ▼
macOS Calendar.app / Reminders.app
        │ iCloud
        ▼
iPhone
```

### 通信协议细节

Claude Code 和 mcp_server.py 之间通过 **stdio**（标准输入/输出）通信，格式是 JSON-RPC。Claude Code 启动 mcp_server.py 进程，双方互相发送 JSON 消息：

```
Claude Code  ──JSON-RPC──►  mcp_server.py
             ◄──JSON-RPC──
```

mcp_server.py 是一个**异步服务**（asyncio），持续监听来自 Claude Code 的工具调用请求。

---

## 模式 B：后台热键服务（当前主要用法）

这是你目前运行的模式，完全独立于 Claude Code，自己内置了一个 AI Agent。

### 涉及文件

| 文件 | 职责 |
|------|------|
| `service.py` | 后台守护进程，监听全局快捷键 |
| `floating_agent.py` | 浮动对话框 UI + OpenAI Agent 逻辑 |
| `calendar_tools.py` | AppleScript 底层工具（两种模式共用）|

### 执行流程（详细）

```
python3 service.py 启动
        │
        ├─► 读取 .env → 加载 OPENAI_API_KEY
        ├─► 创建隐藏的 tk.Tk() 主窗口（不显示）
        ├─► 启动 pynput GlobalHotKeys 监听线程
        └─► 进入 tkinter mainloop()（阻塞等待）

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
用户操作：框选文字 → 按 Ctrl+Shift+Space
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        │
        ▼
pynput 监听线程捕获快捷键
        │
        │  root.after(0, callback)  ← 切换到主线程！
        ▼
simulate_copy()
  ├─ 模拟按下 Cmd+C（pynput 键盘控制器）
  ├─ 等待 150ms（让系统更新剪贴板）
  └─ pbpaste 读取剪贴板内容
        │
        ▼
FloatingDialog(root, text, cursor_pos) 创建对话框
  ├─ 透明窗口 + Canvas 圆角矩形背景
  └─ 显示框选文字预览
        │
        ▼
dialog.start() 启动 Agent
  ├─ 在后台线程运行 _agent_thread()
  └─ 主线程通过 window.after(60ms) 轮询 ui_queue 更新 UI

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_agent_thread()（后台线程）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        │
        ├─ list_calendars()       ← AppleScript 查询
        ├─ list_reminder_lists()  ← AppleScript 查询
        │
        ▼
调用 OpenAI API（gpt-4o-mini，流式输出）
  发送：系统提示（含今日日期、日历列表）+ 用户框选的文本
  tools：create_calendar_event、create_reminder 的描述
        │
        ▼ 流式返回
OpenAI 输出文字 → 实时显示到对话框
OpenAI 决定调用工具 → 组装 tool_call 参数
        │
        ▼
执行工具调用
  ├─ create_calendar_event(**args)
  │       └─ AppleScript → Calendar.app
  └─ create_reminder(**args)
          └─ AppleScript → Reminders.app
        │
        ▼
把工具执行结果返回给 OpenAI（继续对话）
OpenAI 生成最终中文总结
        │
        ▼
对话框显示"✨ 完成！"，iCloud 自动同步到 iPhone
```

### 线程模型

这个项目涉及三个线程，需要小心协调：

```
主线程（tkinter mainloop）
  ├─ 唯一能操作 UI 的线程
  ├─ 通过 root.after() 接收其他线程的 UI 更新请求
  └─ 通过 window.after(60ms, _poll) 不断读取 ui_queue

pynput 监听线程
  ├─ 常驻后台，等待快捷键
  └─ 快捷键触发 → root.after(0, ...) 通知主线程（不直接操作 UI）

Agent 线程（每次弹窗时创建）
  ├─ 负责所有耗时操作：OpenAI API 调用、AppleScript 执行
  └─ 结果通过 ui_queue.put() 发给主线程，不直接操作 UI
```

---

## 底层：AppleScript 如何写入日历

`calendar_tools.py` 没有用任何第三方日历库，而是直接调用 macOS 的 `osascript` 命令执行 AppleScript：

```python
subprocess.run(["osascript", "-e", script], ...)
```

以创建一个日历事件为例，实际执行的 AppleScript 类似：

```applescript
tell application "Calendar"
    set startDate to current date
    set year of startDate to 2026
    set month of startDate to 3
    set day of startDate to 5
    set time of startDate to 36000   -- 10:00:00

    set endDate to current date
    set year of endDate to 2026
    set month of endDate to 3
    set day of endDate to 5
    set time of endDate to 39600     -- 11:00:00

    tell (first calendar whose writable is true)
        make new event at end with properties {
            summary:"团队周会",
            start date:startDate,
            end date:endDate
        }
    end tell
end tell
```

Calendar.app 收到事件后，通过 iCloud 自动推送到 iPhone。

---

## 两种模式对比

| | 模式 A（MCP）| 模式 B（热键服务）|
|---|---|---|
| 入口 | Claude Code CLI | `python3 service.py` |
| AI 来源 | Claude（Pro 订阅）| OpenAI API（需 API Key）|
| 触发方式 | 在 Claude Code 对话中输入 | 框选文字 → Ctrl+Shift+Space |
| 对话框 UI | 无（在终端显示）| 有浮动对话框 |
| 适合场景 | 已经在用 Claude Code 时 | 日常任意应用中随时触发 |
| 费用 | Claude 订阅费内 | OpenAI 按量计费（极少）|

---

## 文件结构总览

```
CalendarAgent/
├── service.py          # 后台热键守护进程
├── floating_agent.py   # 浮动对话框 UI + OpenAI Agent
├── mcp_server.py       # MCP 工具服务器（供 Claude Code 使用）
├── calendar_tools.py   # AppleScript 底层工具（两种模式共用）
├── .env                # API Key 配置（不要提交到 Git）
├── requirements.txt    # Python 依赖
└── setup.sh            # 安装脚本
```
