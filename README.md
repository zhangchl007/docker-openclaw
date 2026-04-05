# OpenClaw Docker — China Stock Analysis# OpenClaw Docker — China Stock Analysis



OpenClaw AI Gateway + automated A-Share & HK stock analysis with WeChat notifications.[OpenClaw](https://openclaw.io) AI Gateway + automated China A-Share & HK stock analysis with WeChat notifications.Docker-based deployment for [OpenClaw](https://openclaw.io) AI Gateway with an integrated **China A-Share & HK Stock Analysis System**, featuring automated reports, multi-master scoring, macro cycle assessment, and WeChat notifications.Docker-based deployment for OpenClaw AI Gateway with **China Stock Analysis**.



**Features:** Deep-dive analysis (RSI/MACD/PE/PB/ROE/PEG) · Three-master scoring (O'Neil/Buffett/Lynch) · Howard Marks market cycle · 10yr financials · Price alerts · Auto holiday skip## Features## ✨ Features



**Watchlist:** 18 stocks / 6 sectors (白酒·新能源·科技·金融·医药·港股) — edit `data/stock-data/watchlist.json`| Feature | Description |

|---------|-------------|

## Schedule| 🦞 OpenClaw AI Gateway | AI agent gateway with conversation management |

| Time | Job || 📊 **Deep-dive stock analysis** | Technical (RSI/MACD/Bollinger) + Fundamental (PE/PB/ROE/PEG) |

|------|-----|| 📊 China A-Share Stock Analysis | (16 stocks in watchlist)

| Mon-Fri 09:00 | Morning brief |

| Mon-Fri 11:35 | Midday update |- 🏆 **Three-master scoring** — CANSLIM (O'Neil) + Value (Buffett/Duan Yongping) + Growth (Peter Lynch)| 🦞 **OpenClaw Gateway** | AI agent gateway with conversation management |- 📱 WeChat Notifications (WeCom Bot / Server酱 / PushPlus)

| Mon-Fri 15:05 | Close summary (deep-dive) |

| Mon-Fri */30min | Price alerts |- 🔄 **Market cycle assessment** — Howard Marks 14-dimension framework with real macro data (GDP/PMI/M2/Bonds/FX)| 📊 **Deep-Dive Stock Analysis** | Technical + fundamental analysis for A-shares and HK stocks |- ⏰ Automated Daily Reports

| Sat 10:00 | Weekly report |

| Biweekly Sat 11:00 | Market cycle analysis |- 📈 **Multi-year financials** — 10-year A-share / 9-year HK history



All daily jobs skip weekends + China public holidays via Sina trading calendar.- 📱 **WeChat notifications** — Auto-send via WeCom webhook (auto-splits long messages)| 🏆 **Three-Master Scoring** | CANSLIM (O'Neil) + Value (Buffett/Duan Yongping) + Growth (Peter Lynch) |- 🔔 Real-time Price Alerts



## Quick Start- ⏰ **Smart scheduling** — Skips weekends + China public holidays automatically

```bash

git clone https://github.com/zhangchl007/docker-openclaw.git && cd docker-openclaw- 🔔 **Price alerts** — Breakout/breakdown monitoring during trading hours| 🔄 **Market Cycle Assessment** | Howard Marks 14-dimension framework with real macro data |

git config core.hooksPath .githooks

docker compose up -d

docker exec -u root openclaw apt-get update && docker exec -u root openclaw apt-get install -y python3-pip

docker exec openclaw pip3 install akshare baostock pandas numpy requests --break-system-packages## Watchlist| 📈 **Multi-Year Financials** | 10-year A-share / 9-year HK stock financial history |## 📅 Automated Schedule

cp data/stock-data/notifier.example.json data/stock-data/notifier.json  # add your WeCom webhook

docker exec -w /home/node/.openclaw/skills/china-stock openclaw python3 runner.py test

```

Dashboard: http://localhost:18789/18 stocks across 6 sectors: 白酒 · 新能源 · 科技 · 金融 · 医药 · 港股 (including 腾讯控股 HK:00700)| 📱 **WeChat Notifications** | Auto-send reports via WeCom webhook |



## Usage

```bash

docker exec -w /home/node/.openclaw/skills/china-stock openclaw python3 report.py --sector 医药   # deep-diveEdit `data/stock-data/watchlist.json` to customize.| ⏰ **Smart Scheduling** | Cron with China trading calendar (holidays excluded) || Time | Report | Description |

docker exec -w /home/node/.openclaw/skills/china-stock openclaw python3 market_cycle.py --send    # macro cycle → WeChat

docker exec -w /home/node/.openclaw/skills/china-stock openclaw python3 runner.py weekly          # weekly report → WeChat

```

## Schedule| 🔔 **Price Alerts** | Real-time price breakout/breakdown alerts ||------|--------|-------------|

## Data Sources

| Data | A-Shares | HK | API |

|------|----------|-----|-----|

| Quotes (PE/PB) | ✅ | ✅ | Tencent/Sina || Time | Job || 09:00 | 🌅 早盘简报 | Morning brief with market overview |

| K-lines | ✅ | ✅ | Baostock/AKShare |

| Financials | ✅ 10yr | ✅ 9yr | AKShare ||------|-----|

| Macro | ✅ | — | AKShare |

| Mon-Fri 09:00 | 🌅 Morning brief |## 📅 Automated Schedule| 11:35 | 🕛 午盘快报 | Midday update with top gainers/losers |

All cached locally. Repeat runs < 1 second.

| Mon-Fri 11:35 | 🕛 Midday update |

## Structure

```| Mon-Fri 15:05 | 📊 Close summary (deep-dive) || 15:05 | 📊 收盘总结 | Close summary with full analysis |

data/stock-data/watchlist.json       # your stocks

data/stock-data/notifier.json        # WeChat config| Mon-Fri */30min | ⚠️ Price alerts |

data/skills/china-stock/

  stock_data.py   # data layer (Sina/Tencent/Baostock/AKShare + cache)| Saturday 10:00 | 📈 Weekly report || Time | Job | Description || */30 min | ⚠️ 价格预警 | Price alert check during trading hours |

  analyzers.py    # CANSLIM + Value + Growth scoring

  report.py       # deep-dive report generator| Biweekly Sat 11:00 | 🔄 Market cycle analysis |

  market_cycle.py # Howard Marks 14-dim macro analysis

  runner.py       # cron entry + trading calendar|------|-----|-------------|| Sat 10:00 | 📈 股票周报 | Weekly performance report |

  notifier.py     # WeChat sender (auto-split long msgs)

```## Quick Start



## Security| Mon-Fri 09:00 | 🌅 Morning Brief | Watchlist overview + price alerts setup |

Gateway on `127.0.0.1` only · `no-new-privileges` · `.gitignore` + pre-commit hook protects secrets

```bash

## Logs

```bashgit clone https://github.com/zhangchl007/docker-openclaw.git| Mon-Fri 11:35 | 🕛 Midday Update | Top gainers/losers at midday break |## 🚀 Quick Start

docker compose logs -f                                                          # gateway

cat data/stock-data/logs/stock-$(date +%Y%m%d).log                              # analysiscd docker-openclaw

```

git config core.hooksPath .githooks| Mon-Fri 15:05 | 📊 Close Summary | Full deep-dive analysis with technicals |

docker compose up -d

| Mon-Fri */30min | ⚠️ Price Alert | Breakout/breakdown checks during trading hours |```bash

# Install dependencies

docker exec -u root openclaw apt-get update && docker exec -u root openclaw apt-get install -y python3-pip| Saturday 10:00 | 📈 Weekly Report | All-stock deep-dive with 3-master scoring |# Clone the repository

docker exec openclaw pip3 install akshare baostock pandas numpy requests --break-system-packages

| Biweekly Sat 11:00 | 🔄 Market Cycle | Howard Marks macro cycle assessment |git clone https://github.com/zhangchl007/docker-openclaw.git

# Configure WeChat (paste your WeCom webhook URL)

cp data/stock-data/notifier.example.json data/stock-data/notifier.jsoncd docker-openclaw

# Edit data/stock-data/notifier.json

> **Note:** All daily jobs automatically skip weekends and China public holidays (Spring Festival, National Day, Qingming, etc.) using the Sina trading calendar API.

# Test

docker exec -w /home/node/.openclaw/skills/china-stock openclaw python3 runner.py test# Enable pre-commit security hook

```

## 📂 Project Structuregit config core.hooksPath .githooks

Dashboard: http://localhost:18789/

```# Start the gateway

## Usage

docker-openclaw/docker compose up -d

```bash

# Deep-dive report (all stocks or specific sector)├── docker-compose.yml              # Container orchestration

docker exec -w /home/node/.openclaw/skills/china-stock openclaw python3 report.py

docker exec -w /home/node/.openclaw/skills/china-stock openclaw python3 report.py --sector 医药├── openclaw.example.json           # Example gateway config# Install Python dependencies



# Market cycle analysis (Howard Marks framework)├── .gitignore                      # Security: protects sensitive filesdocker exec -u root openclaw apt-get update && docker exec -u root openclaw apt-get install -y python3-pip

docker exec -w /home/node/.openclaw/skills/china-stock openclaw python3 market_cycle.py

├── .githooks/pre-commit            # Secret scanning hookdocker exec openclaw pip3 install akshare pandas numpy --break-system-packages

# Send any report to WeChat

docker exec -w /home/node/.openclaw/skills/china-stock openclaw python3 market_cycle.py --refresh --send├── .github/```



# View financial history│   ├── copilot-instructions.md     # GitHub Copilot context

docker exec -w /home/node/.openclaw/skills/china-stock openclaw python3 -c "

from stock_data import get_provider│   └── INVESTMENT_PHILOSOPHY.md    # Three-master methodology docs## 🌐 Access Dashboard

p = get_provider()

for f in p.get_financial_history('600519'):│

    print(f'{f[\"year\"]} ROE:{f[\"roe\"]:.1f}% GM:{f[\"gross_margin\"]:.1f}%')

p.cleanup()└── data/                           # Mounted as /home/node/.openclawOpen in browser: http://localhost:18789/

"

```    ├── openclaw.json               # Gateway config (sensitive!)



## Data Sources    ├── cron/jobs.json              # 6 scheduled jobs## 📊 Stock Analysis Setup



| Data | A-Shares | HK Stocks | API |    ├── stock-data/

|------|----------|-----------|-----|

| Quotes (PE/PB) | ✅ | ✅ | Tencent / Sina |    │   ├── watchlist.json          # 18 stocks across 6 sectors + alerts### Step 1: Configure Watchlist

| Daily K-lines | ✅ | ✅ | Baostock / AKShare |

| Financials (10yr/9yr) | ✅ | ✅ | AKShare (同花顺/东方财富) |    │   ├── notifier.json           # WeChat notification config

| Macro (GDP/PMI/M2/Bonds) | ✅ | — | AKShare |

| Trading calendar | ✅ | — | Sina |    │   ├── market-cycle.json       # Howard Marks manual overridesEdit `data/stock-data/watchlist.json` to add your stocks:



All data cached locally. Second runs < 1 second.    │   └── cache/                  # Auto-managed data cache



## Project Structure    │```json



```    └── skills/china-stock/         # Stock analysis skill (6 Python files){

data/

├── stock-data/        ├── stock_data.py           # Data layer (Sina/Tencent/Baostock/AKShare)  "groups": {

│   ├── watchlist.json        # Your stocks

│   ├── notifier.json         # WeChat config        ├── analyzers.py            # 3-master scoring (pure computation)    "我的自选": [

│   └── market-cycle.json     # Macro cycle overrides

└── skills/china-stock/        ├── report.py               # Deep-dive report generator      {"code": "600519", "name": "贵州茅台", "market": "SH"}

    ├── stock_data.py          # Data layer (all API calls + caching)

    ├── analyzers.py           # CANSLIM + Value + Growth scoring        ├── market_cycle.py         # Howard Marks macro cycle analyzer    ]

    ├── report.py              # Deep-dive report generator

    ├── market_cycle.py        # Howard Marks 14-dim macro analysis        ├── runner.py               # Cron entry point + trading calendar  }

    ├── runner.py              # Cron entry + trading calendar

    └── notifier.py            # WeChat sender (auto-split)        ├── notifier.py             # Multi-channel notification sender}

```

        └── skill.json              # Skill manifest```

## Security

```

- Gateway binds to `127.0.0.1` only

- Container runs with `no-new-privileges`, dropped `NET_RAW`/`NET_ADMIN`### Step 2: Configure WeChat Notifications

- `.gitignore` + pre-commit hook protects secrets (`data/openclaw.json`, `data/identity/`, `data/stock-data/notifier.json`)

## 🗂️ Watchlist (18 Stocks, 6 Sectors)

## Logs

```bash

```bash

docker compose logs -f                           # Gateway| Sector | Stocks |# Copy example config

cat data/stock-data/logs/stock-$(date +%Y%m%d).log  # Analysis

```|--------|--------|cp data/stock-data/notifier.example.json data/stock-data/notifier.json


| 白酒 | 贵州茅台, 五粮液, 泸州老窖 |

| 新能源 | 宁德时代, 比亚迪, 通威股份 |# Edit with your keys (choose one or more):

| 科技 | 海康威视, 东方财富, 科大讯飞 |# - WeCom Bot Webhook (企业微信机器人)

| 金融 | 中国平安, 招商银行, 兴业银行 |# - Server酱 SendKey (推送到微信)

| 医药 | 泰格医药, 康龙化成, 开立医疗, 昊海生科, 达意隆 |# - PushPlus Token

| 港股 | 腾讯控股 (HK:00700) |# - Telegram Bot

```

Edit `data/stock-data/watchlist.json` to customize.

### Step 3: Test the System

## 📊 Data Sources

```bash

| Data | A-Shares | HK Stocks | Source |# Test all components

|------|----------|-----------|--------|docker exec openclaw python3 /home/node/.openclaw/skills/china-stock/runner.py test

| Real-time Quotes | ✅ (PE/PB) | ✅ | Tencent API / Sina API |

| Daily K-Lines | ✅ 120 days | ✅ 120 days | Baostock / AKShare (Sina) |# Fetch real-time quotes

| Financial History | ✅ 10 years | ✅ 9 years | AKShare (同花顺/东方财富) |docker exec openclaw python3 /home/node/.openclaw/skills/china-stock/collector.py --action quotes --output table

| Latest Financials | ✅ ROE/Margins | ✅ ROE/Margins | Baostock / AKShare |

| Macro Data | ✅ GDP/PMI/M2/LPR/Bonds | — | AKShare |# Generate and view daily report

| Trading Calendar | ✅ Holidays | — | Sina API |docker exec openclaw python3 /home/node/.openclaw/skills/china-stock/analyzer.py --report daily



**Caching:** All API data is cached locally (quotes: 1min, K-lines: 4hr, financials: 24hr, macro: 4hr). Second runs complete in < 1 second.# Test notification (after configuring notifier.json)

docker exec openclaw python3 /home/node/.openclaw/skills/china-stock/notifier.py --test --channel wecom

## 🚀 Quick Start```



### 1. Clone & Start### Step 4: Verify Scheduled Jobs



```bash```bash

git clone https://github.com/zhangchl007/docker-openclaw.git# List all cron jobs

cd docker-openclawdocker exec openclaw openclaw cron list



# Enable security hook# Manually run a job

git config core.hooksPath .githooksdocker exec openclaw openclaw cron run stock-morning



# Start the gateway# Check cron status

docker compose up -ddocker exec openclaw openclaw cron status

``````



### 2. Install Dependencies## 📱 WeChat Notification Setup



```bash### Option 1: WeCom Bot (企业微信机器人) - Recommended

docker exec -u root openclaw apt-get update

docker exec -u root openclaw apt-get install -y python3-pip1. 在企业微信群中，点击右上角 `...` → `添加群机器人`

docker exec openclaw pip3 install akshare baostock pandas numpy requests --break-system-packages2. 复制 Webhook 地址

```3. 编辑 `data/stock-data/notifier.json`:

   ```json

### 3. Configure WeChat Notifications   {

     "wecom": {

```bash       "webhook": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY"

cp data/stock-data/notifier.example.json data/stock-data/notifier.json     }

# Edit data/stock-data/notifier.json with your WeCom webhook URL   }

```   ```
**WeCom Bot setup** (recommended):### Option 2: Server酱 (推送到微信)

1. Open any WeCom group → `...` → Add Group Bot

2. Copy the webhook URL1. 访问 https://sct.ftqq.com/ 注册

3. Paste into `notifier.json` under `wecom.webhook`2. 获取 SendKey

3. 编辑 `data/stock-data/notifier.json`:

### 4. Test   ```json

   {

```bash     "serverchan": {

# Test all components       "sendkey": "YOUR_SENDKEY"

docker exec -w /home/node/.openclaw/skills/china-stock openclaw python3 runner.py test     }

   }

# Generate deep-dive report (medical sector)   ```

docker exec -w /home/node/.openclaw/skills/china-stock openclaw python3 report.py --sector 医药

### Option 3: PushPlus

# Run market cycle analysis

docker exec -w /home/node/.openclaw/skills/china-stock openclaw python3 market_cycle.py1. 访问 https://www.pushplus.plus/ 注册

2. 获取 Token

# Send report to WeChat3. 编辑 `data/stock-data/notifier.json`

docker exec -w /home/node/.openclaw/skills/china-stock openclaw python3 market_cycle.py --send

```## ⚙️ Configuration



## 🌐 Access DashboardEdit `data/openclaw.json` or use CLI:



``````bash

http://localhost:18789/docker exec openclaw openclaw config set <key> <value>

``````

## 📊 Analysis Reports## 📋 Logs

### Deep-Dive Stock Report (`report.py`)```bash

# OpenClaw gateway logs

Each stock receives:docker compose logs -f

- **Core metrics**: PE, PB, ROE, PEG, margins, growth rates

- **Technical analysis**: RSI, MACD, Bollinger Bands, MA support/resistance, volatility# Stock analysis logs

- **Three-master scoring**: CANSLIM + Value + Growth (weighted 30/35/35)docker exec openclaw cat /home/node/.openclaw/stock-data/logs/stock-$(date +%Y%m%d).log

- **Investment commentary**: Auto-generated insights and risk warnings```

```bash## 🔒 Security

# All sectors

docker exec -w /home/node/.openclaw/skills/china-stock openclaw python3 report.py⚠️ **Important Security Notes:**

# Specific sector- Gateway only listens on localhost (127.0.0.1)

docker exec -w /home/node/.openclaw/skills/china-stock openclaw python3 report.py --sector 白酒- Token-based authentication enabled

```- Container runs with reduced privileges

- **NEVER commit the `data/` directory contents** (except `canvas/`)

### Market Cycle Report (`market_cycle.py`)- The `.gitignore` protects sensitive files, but always verify before pushing

- Use the pre-commit hook: `git config core.hooksPath .githooks`

Howard Marks' 14-dimension assessment using **real macro data**:

### Sensitive Files (Protected by .gitignore)

| Dimension | Data Source |

|-----------|-----------|| Path | Contains |

| Economy (GDP/PMI) | AKShare: `macro_china_gdp`, `macro_china_pmi` ||------|----------|

| Money Supply (M2/M1) | AKShare: `macro_china_money_supply` || `data/openclaw.json` | Auth tokens |

| Bond Yields (10Y/2Y spread) | AKShare: `bond_zh_us_rate` || `data/identity/` | Private keys |

| Margin Trading | AKShare: `stock_margin_sse` || `data/devices/` | Device tokens |

| FX Rate (USD/CNY) | AKShare: `currency_boc_sina` || `data/stock-data/notifier.json` | API keys |

| IPO Pipeline | AKShare: `stock_ipo_info` || `data/logs/` | May contain sensitive info |

| Stock Buybacks | AKShare: `stock_repurchase_em` |

| Market Performance | Baostock: SH/CSI300/ChiNext indices |### Verify Before Pushing

| Volume & Volatility | Baostock: Shanghai index |

```bash

Output: cycle position score (-14 to +14) with position strategy, sector allocation, and risk warnings.# Check what will be committed

git status

```bash

# View report# Ensure no secrets are staged

docker exec -w /home/node/.openclaw/skills/china-stock openclaw python3 market_cycle.pygit diff --cached --name-only | grep -E "data/(openclaw|identity|devices)" && echo "WARNING: Secrets detected!"

```

# Force refresh data + send to WeChat

docker exec -w /home/node/.openclaw/skills/china-stock openclaw python3 market_cycle.py --refresh --send## Documentation

```

- [Requirements & Architecture](.github/openclaw-manual.md)

### Financial History- [Stock Skill Documentation](data/skills/china-stock/SKILL.md)


```bash
# View 10-year financials for any A-share stock
docker exec -w /home/node/.openclaw/skills/china-stock openclaw python3 -c "
from stock_data import get_provider
p = get_provider()
for f in p.get_financial_history('600519'):  # 贵州茅台
    print(f'{f[\"year\"]} ROE:{f[\"roe\"]:.1f}% 毛利:{f[\"gross_margin\"]:.1f}% 净利增:{f[\"profit_growth\"]:+.1f}%')
p.cleanup()
"
```
## 📋 Logs

```bash
# Gateway logs
docker compose logs -f

# Stock analysis logs (daily)
docker exec openclaw cat /home/node/.openclaw/stock-data/logs/stock-$(date +%Y%m%d).log
```

## 🔒 Security

| Measure | Details |
|---------|---------|
| Network | Gateway listens on `127.0.0.1` only |
| Auth | Token-based authentication |
| Container | `no-new-privileges`, dropped `NET_RAW`/`NET_ADMIN` |
| Git | `.gitignore` + pre-commit hook blocks secrets |
| Secrets | `data/openclaw.json`, `data/identity/`, `data/devices/`, `data/stock-data/notifier.json` |

```bash
# Verify no secrets will be committed
git status
git diff --cached --name-only | grep -E "data/(openclaw|identity|devices)" && echo "⚠️ SECRETS!"
```

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────┐
│                   Cron Scheduler                 │
│  morning │ midday │ close │ alert │ weekly │ cycle│
└────┬─────┴───┬────┴───┬───┴───┬───┴───┬────┴──┬──┘
     │         │        │       │       │       │
     ▼         ▼        ▼       ▼       ▼       ▼
┌─────────────────────┐  ┌──────────────────────────┐
│     runner.py        │  │    market_cycle.py        │
│  + TradingCalendar   │  │  Howard Marks 14-dim      │
└─────────┬───────────┘  └────────────┬─────────────┘
          │                           │
          ▼                           ▼
┌─────────────────────┐  ┌──────────────────────────┐
│    report.py         │  │     AKShare Macro APIs    │
│  Deep-dive generator │  │  GDP/PMI/M2/Bonds/FX/IPO │
└─────────┬───────────┘  └──────────────────────────┘
          │
          ▼
┌─────────────────────┐
│   analyzers.py       │
│  CANSLIM+Value+Growth│
│  (pure computation)  │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────────────────────────────────┐
│              stock_data.py (Data Layer)           │
│                                                   │
│  Quotes:  Tencent API (A-share PE/PB)            │
│           Sina API    (A-share + HK stocks)       │
│  History: Baostock    (A-share daily K-lines)     │
│           AKShare     (HK stock daily K-lines)    │
│  Finance: Baostock    (A-share latest quarter)    │
│           AKShare     (A/HK multi-year history)   │
│                                                   │
│  Cache: file-based + in-memory, auto TTL          │
└─────────────────────┬───────────────────────────┘
                      │
                      ▼
              ┌───────────────┐
              │  notifier.py   │
              │  WeCom webhook │
              │  (auto-split)  │
              └───────────────┘
```
## 📖 Documentation

- [Investment Philosophy](.github/INVESTMENT_PHILOSOPHY.md) — CANSLIM, Value, Growth methodologies
- [Skill Documentation](data/skills/china-stock/SKILL.md) — Technical details
- [WeCom Setup Guide](data/stock-data/WECOM_SETUP.md) — WeChat notification setup

## License

Private project. Not for redistribution.
