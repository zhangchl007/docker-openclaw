# OpenClaw Docker Deployment

Docker-based deployment for OpenClaw AI Gateway with **China Stock Analysis**.

## ✨ Features

- 🦞 OpenClaw AI Gateway
- 📊 China A-Share Stock Analysis (16 stocks in watchlist)
- 📱 WeChat Notifications (WeCom Bot / Server酱 / PushPlus)
- ⏰ Automated Daily Reports
- 🔔 Real-time Price Alerts

## 📅 Automated Schedule

| Time | Report | Description |
|------|--------|-------------|
| 09:00 | 🌅 早盘简报 | Morning brief with market overview |
| 11:35 | 🕛 午盘快报 | Midday update with top gainers/losers |
| 15:05 | 📊 收盘总结 | Close summary with full analysis |
| */30 min | ⚠️ 价格预警 | Price alert check during trading hours |
| Sat 10:00 | 📈 股票周报 | Weekly performance report |

## 🚀 Quick Start

```bash
# Clone the repository
git clone https://github.com/zhangchl007/docker-openclaw.git
cd docker-openclaw

# Enable pre-commit security hook
git config core.hooksPath .githooks

# Start the gateway
docker compose up -d

# Install Python dependencies
docker exec -u root openclaw apt-get update && docker exec -u root openclaw apt-get install -y python3-pip
docker exec openclaw pip3 install akshare pandas numpy --break-system-packages
```

## 🌐 Access Dashboard

Open in browser: http://localhost:18789/

## 📊 Stock Analysis Setup

### Step 1: Configure Watchlist

Edit `data/stock-data/watchlist.json` to add your stocks:

```json
{
  "groups": {
    "我的自选": [
      {"code": "600519", "name": "贵州茅台", "market": "SH"}
    ]
  }
}
```

### Step 2: Configure WeChat Notifications

```bash
# Copy example config
cp data/stock-data/notifier.example.json data/stock-data/notifier.json

# Edit with your keys (choose one or more):
# - WeCom Bot Webhook (企业微信机器人)
# - Server酱 SendKey (推送到微信)
# - PushPlus Token
# - Telegram Bot
```

### Step 3: Test the System

```bash
# Test all components
docker exec openclaw python3 /home/node/.openclaw/skills/china-stock/runner.py test

# Fetch real-time quotes
docker exec openclaw python3 /home/node/.openclaw/skills/china-stock/collector.py --action quotes --output table

# Generate and view daily report
docker exec openclaw python3 /home/node/.openclaw/skills/china-stock/analyzer.py --report daily

# Test notification (after configuring notifier.json)
docker exec openclaw python3 /home/node/.openclaw/skills/china-stock/notifier.py --test --channel wecom
```

### Step 4: Verify Scheduled Jobs

```bash
# List all cron jobs
docker exec openclaw openclaw cron list

# Manually run a job
docker exec openclaw openclaw cron run stock-morning

# Check cron status
docker exec openclaw openclaw cron status
```

## 📱 WeChat Notification Setup

### Option 1: WeCom Bot (企业微信机器人) - Recommended

1. 在企业微信群中，点击右上角 `...` → `添加群机器人`
2. 复制 Webhook 地址
3. 编辑 `data/stock-data/notifier.json`:
   ```json
   {
     "wecom": {
       "webhook": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY"
     }
   }
   ```

### Option 2: Server酱 (推送到微信)

1. 访问 https://sct.ftqq.com/ 注册
2. 获取 SendKey
3. 编辑 `data/stock-data/notifier.json`:
   ```json
   {
     "serverchan": {
       "sendkey": "YOUR_SENDKEY"
     }
   }
   ```

### Option 3: PushPlus

1. 访问 https://www.pushplus.plus/ 注册
2. 获取 Token
3. 编辑 `data/stock-data/notifier.json`

## ⚙️ Configuration

Edit `data/openclaw.json` or use CLI:

```bash
docker exec openclaw openclaw config set <key> <value>
```

## 📋 Logs

```bash
# OpenClaw gateway logs
docker compose logs -f

# Stock analysis logs
docker exec openclaw cat /home/node/.openclaw/stock-data/logs/stock-$(date +%Y%m%d).log
```

## 🔒 Security

⚠️ **Important Security Notes:**

- Gateway only listens on localhost (127.0.0.1)
- Token-based authentication enabled
- Container runs with reduced privileges
- **NEVER commit the `data/` directory contents** (except `canvas/`)
- The `.gitignore` protects sensitive files, but always verify before pushing
- Use the pre-commit hook: `git config core.hooksPath .githooks`

### Sensitive Files (Protected by .gitignore)

| Path | Contains |
|------|----------|
| `data/openclaw.json` | Auth tokens |
| `data/identity/` | Private keys |
| `data/devices/` | Device tokens |
| `data/stock-data/notifier.json` | API keys |
| `data/logs/` | May contain sensitive info |

### Verify Before Pushing

```bash
# Check what will be committed
git status

# Ensure no secrets are staged
git diff --cached --name-only | grep -E "data/(openclaw|identity|devices)" && echo "WARNING: Secrets detected!"
```

## Documentation

- [Requirements & Architecture](.github/openclaw-manual.md)
- [Stock Skill Documentation](data/skills/china-stock/SKILL.md)
