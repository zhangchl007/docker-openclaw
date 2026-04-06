# OpenClaw Docker — China Stock Analysis

Automated China A-share & HK stock analysis system powered by [OpenClaw](https://openclaw.com) gateway. Combines three investment methodologies (CANSLIM, Value Investing, Growth) with macro cycle analysis, delivering actionable insights via WeChat.

## ✨ Features

- **Multi-Master Scoring** — CANSLIM (O'Neil) + Value (Duan Yongping) + Growth (Peter Lynch)
- **Technical Analysis** — MA, RSI, MACD, Bollinger Bands, volume analysis
- **Fundamental Analysis** — PE, PB, ROE, PEG, 10-year financial history
- **Macro Cycle Analysis** — Howard Marks 14-dimension market cycle positioning
- **Trading Signals** — Multi-dimension buy/sell signals with pattern recognition
- **Automated Reports** — Morning briefing, midday update, closing summary, weekly report
- **Price Alerts** — Configurable thresholds checked every 30 minutes during trading hours
- **WeChat Delivery** — Auto-split long messages, supports WeCom App/Bot, Server酱, PushPlus, Telegram

## 🚀 Quick Start

### Prerequisites

- Docker & Docker Compose
- An OpenClaw account and gateway token

### 1. Clone & Configure

```bash
git clone <repo-url> && cd openclaw-docker

# Copy example config
cp openclaw.example.json data/openclaw.json
# Edit data/openclaw.json — set your gateway token

# Configure notifications
cp data/stock-data/notifier.example.json data/stock-data/notifier.json
# Edit data/stock-data/notifier.json — set your WeChat webhook key

# Enable security hook
git config core.hooksPath .githooks
```

### 2. Start

```bash
docker compose up -d
```

### 3. Install Dependencies (first time)

```bash
docker exec openclaw pip3 install akshare baostock pandas numpy requests
```

### 4. Configure Watchlist

Edit `data/stock-data/watchlist.json` to add your stocks:

```json
{
  "groups": {
    "核心持仓": ["600519", "000858"],
    "科技成长": ["300750", "hk00700"],
    "金融地产": ["601318", "000002"]
  }
}
```

### 5. Test

```bash
# Run a closing report
docker exec -w /home/node/.openclaw/skills/china-stock openclaw python3 runner.py close

# Run market cycle analysis
docker exec -w /home/node/.openclaw/skills/china-stock openclaw python3 market_cycle.py

# Force refresh + send to WeChat
docker exec -w /home/node/.openclaw/skills/china-stock openclaw python3 market_cycle.py --refresh --send
```

## ⏰ Cron Schedule

| Job | Time | Command |
|-----|------|---------|
| 早盘简报 | 9:00 Mon-Fri | `python3 runner.py morning` |
| 午盘快报 | 11:35 Mon-Fri | `python3 runner.py midday` |
| 收盘总结 | 15:05 Mon-Fri | `python3 runner.py close` |
| 价格预警 | Every 30min (trading hours) | `python3 runner.py alert` |
| 周报 | Sat 10:00 | `python3 runner.py weekly` |
| 周期分析 | Sat 10:30 | `python3 market_cycle.py --send` |

All jobs auto-skip weekends and Chinese public holidays via `TradingCalendar`.

## 📊 Data Sources

| Data | Source |
|------|--------|
| Real-time Quotes | Sina Finance API |
| Daily K-lines (A-share) | Baostock |
| Daily K-lines (HK) | AKShare |
| Financials (latest) | Baostock |
| Financials (10yr history) | AKShare |
| GDP / PMI / CPI / M2 | AKShare (NBS) |
| Bond Yields | AKShare (10Y gov bonds) |
| Margin Trading | AKShare: `stock_margin_sse` |
| FX Rate (USD/CNY) | AKShare: `currency_boc_sina` |
| IPO Pipeline | AKShare: `stock_ipo_info` |
| Stock Buybacks | AKShare: `stock_repurchase_em` |
| Market Indices | Baostock: SH/CSI300/ChiNext |

## 🔧 Manual Commands

```bash
# View 10-year financials
docker exec -w /home/node/.openclaw/skills/china-stock openclaw python3 -c "
from stock_data import get_provider
p = get_provider()
for f in p.get_financial_history('600519'):
    print(f'{f[\"year\"]} ROE:{f[\"roe\"]:.1f}% 毛利:{f[\"gross_margin\"]:.1f}% 净利增:{f[\"profit_growth\"]:+.1f}%')
p.cleanup()
"

# Manually run any cron job
docker exec -w /home/node/.openclaw/skills/china-stock openclaw python3 runner.py close

# Check cron status
docker exec openclaw cat /home/node/.openclaw/cron/jobs.json
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
┌───────────────────────────────────────────────────┐
│              analyzers.py                          │
│  CANSLIM │ Value │ Growth │ TechCalc │ Signals    │
└─────────────────────┬─────────────────────────────┘
                      │
                      ▼
┌───────────────────────────────────────────────────┐
│              stock_data.py                         │
│                                                   │
│  Quotes:  Sina Finance (real-time A+HK)           │
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

### Key Files

```
stock_data.py   → Data layer (Sina/Tencent/Baostock/AKShare + cache)
analyzers.py    → CANSLIM + Value + Growth scoring (pure computation)
report.py       → Deep-dive report with 10yr financials + technicals
market_cycle.py → Howard Marks 14-dim macro analysis (real GDP/PMI/M2/Bonds)
trading.py      → Multi-dimension trading signals (trend/momentum/volume/pattern)
runner.py       → Cron entry + China trading calendar (auto skip holidays)
notifier.py     → WeChat sender (auto-split long messages)
```

### Stock Code Format

- **A-shares**: 6-digit (e.g., `600519` for 茅台)
- **HK stocks**: prefix `hk` (e.g., `hk00700` for 腾讯)
- **Indices**: `000001` (上证), `000300` (沪深300), `399006` (创业板指)

## 📖 Documentation

- [Investment Philosophy](.github/INVESTMENT_PHILOSOPHY.md) — CANSLIM, Value, Growth methodologies
- [Requirements & Architecture](.github/openclaw-manual.md) — Full system design
- [Skill Documentation](data/skills/china-stock/SKILL.md) — Technical details
- [WeCom Setup Guide](data/stock-data/WECOM_SETUP.md) — WeChat notification setup

## License

Private project. Not for redistribution.
