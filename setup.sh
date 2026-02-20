#!/bin/bash
# setup.sh - 安装 CalendarAgent 依赖并注册 MCP 服务器

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="python3"

echo "📦  安装 Python 依赖..."
$PYTHON -m pip install openai mcp pynput

echo ""
echo "✅  依赖安装完成！"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  接下来的设置步骤"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "1️⃣   配置 OpenAI API Key："
echo "     编辑 $SCRIPT_DIR/.env，填入："
echo "     OPENAI_API_KEY=sk-proj-..."
echo ""
echo "2️⃣   注册 MCP 服务器到 Claude Code："
echo "     claude mcp add calendar-agent $PYTHON $SCRIPT_DIR/mcp_server.py"
echo ""
echo "3️⃣   安装 /calendar Skill 到 Claude Code："
COMMANDS_DIR="$HOME/.claude/commands/calendar"
echo "     目标目录：$COMMANDS_DIR"
if [ ! -d "$COMMANDS_DIR" ]; then
    echo "     （目录不存在，请先运行 /calendar skill 或手动创建）"
else
    echo "     ✅  Skill 已安装"
fi
echo ""
echo "4️⃣   启动后台热键服务（框选文字 → Ctrl+Shift+Space 触发）："
echo "     $PYTHON $SCRIPT_DIR/service.py"
echo ""
echo "     首次运行需在「系统设置 → 隐私与安全性 → 辅助功能」中授权 Terminal"
echo ""
echo "🎉  设置完成！详见 ARCHITECTURE.md"
