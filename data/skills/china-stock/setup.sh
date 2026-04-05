#!/bin/bash
# Setup script for China Stock skill
# 安装中国股票技能依赖

set -e

echo "🦞 OpenClaw China Stock Skill Setup"
echo "=================================="

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 not found. Please install Python 3.9+"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "✓ Python version: $PYTHON_VERSION"

# Install dependencies
echo ""
echo "📦 Installing dependencies..."
pip3 install --upgrade pip
pip3 install -r /home/node/.openclaw/skills/china-stock/requirements.txt

# Verify installation
echo ""
echo "🔍 Verifying installation..."
python3 -c "import akshare; print(f'✓ AKShare version: {akshare.__version__}')"
python3 -c "import pandas; print(f'✓ Pandas version: {pandas.__version__}')"

# Create directories
echo ""
echo "📁 Creating directories..."
mkdir -p /home/node/.openclaw/stock-data/cache
mkdir -p /home/node/.openclaw/stock-data/reports

# Test data fetch
echo ""
echo "🧪 Testing data fetch..."
python3 /home/node/.openclaw/skills/china-stock/collector.py --action indices --output table

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit watchlist: /home/node/.openclaw/stock-data/watchlist.json"
echo "2. Configure notifications: copy notifier.example.json to notifier.json"
echo "3. Set up cron jobs for scheduled reports"
