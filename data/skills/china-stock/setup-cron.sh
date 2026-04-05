#!/bin/bash
# Setup Cron Jobs for Stock Analysis
# 设置股票分析定时任务

set -e

SKILL_PATH="/home/node/.openclaw/skills/china-stock"
PYTHON_CMD="python3"

echo "🦞 OpenClaw Stock Analysis - Cron Setup"
echo "========================================"
echo ""

# Check if runner exists
if [ ! -f "$SKILL_PATH/runner.py" ]; then
    echo "❌ Error: runner.py not found at $SKILL_PATH"
    exit 1
fi

# Test Python and dependencies
echo "📦 Checking dependencies..."
$PYTHON_CMD -c "import akshare, pandas, numpy" 2>/dev/null || {
    echo "❌ Error: Required Python packages not installed"
    echo "   Run: pip3 install akshare pandas numpy --break-system-packages"
    exit 1
}
echo "   ✓ All dependencies installed"

# Check notification config
echo ""
echo "📱 Checking notification config..."
if [ -f "/home/node/.openclaw/stock-data/notifier.json" ]; then
    echo "   ✓ notifier.json found"
else
    echo "   ⚠️  notifier.json not found"
    echo "   Copy from notifier.example.json and add your keys"
fi

echo ""
echo "⏰ Setting up cron jobs..."

# Remove existing stock-related cron jobs
echo "   Removing old jobs..."
for job in stock-morning stock-midday stock-close stock-alert stock-weekly; do
    openclaw cron rm "$job" 2>/dev/null || true
done

# Add new cron jobs
# Note: All times are in container timezone (Asia/Shanghai)

echo "   Adding morning brief (9:00 AM Mon-Fri)..."
openclaw cron add \
    --name "stock-morning" \
    --schedule "0 9 * * 1-5" \
    --command "$PYTHON_CMD $SKILL_PATH/runner.py morning" \
    --description "早盘简报"

echo "   Adding midday update (11:35 AM Mon-Fri)..."
openclaw cron add \
    --name "stock-midday" \
    --schedule "35 11 * * 1-5" \
    --command "$PYTHON_CMD $SKILL_PATH/runner.py midday" \
    --description "午盘快报"

echo "   Adding close summary (15:05 PM Mon-Fri)..."
openclaw cron add \
    --name "stock-close" \
    --schedule "5 15 * * 1-5" \
    --command "$PYTHON_CMD $SKILL_PATH/runner.py close" \
    --description "收盘总结"

echo "   Adding price alerts (every 30 min during trading hours)..."
openclaw cron add \
    --name "stock-alert" \
    --schedule "*/30 9-15 * * 1-5" \
    --command "$PYTHON_CMD $SKILL_PATH/runner.py alert" \
    --description "价格预警检查"

echo "   Adding weekly report (Saturday 10:00 AM)..."
openclaw cron add \
    --name "stock-weekly" \
    --schedule "0 10 * * 6" \
    --command "$PYTHON_CMD $SKILL_PATH/runner.py weekly" \
    --description "股票周报"

echo ""
echo "✅ Cron jobs setup complete!"
echo ""
echo "📋 Current cron jobs:"
openclaw cron list

echo ""
echo "🔧 Management commands:"
echo "   openclaw cron list          # 查看所有任务"
echo "   openclaw cron status        # 查看调度器状态"
echo "   openclaw cron run <name>    # 手动运行任务"
echo "   openclaw cron disable <name> # 禁用任务"
echo "   openclaw cron enable <name>  # 启用任务"
echo ""
echo "🧪 Test commands:"
echo "   $PYTHON_CMD $SKILL_PATH/runner.py test    # 测试所有组件"
echo "   $PYTHON_CMD $SKILL_PATH/runner.py morning # 手动运行早盘简报"
