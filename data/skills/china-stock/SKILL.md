# China Stock Analysis Skill# China Stock Analysis Skill (中国股票分析技能)



## What It Does## Overview

This skill collects and analyzes China A-share stock data, generating reports and sending notifications.

Automated stock analysis platform for China A-shares and HK stocks. Generates deep-dive reports, trading signals, and macro cycle assessments. Sends results to WeChat via WeCom webhook.

## Capabilities

## Files

### 1. Data Collection

| File | Purpose |- Real-time stock quotes (实时行情)

|------|---------|- Daily OHLCV data (日K线数据)

| `stock_data.py` | Data layer — Tencent/Sina (quotes), Baostock (A-share K-lines), AKShare (HK K-lines, macro data, multi-year financials). All cached. |- Technical indicators (技术指标): MA, MACD, RSI, KDJ

| `analyzers.py` | Three-master scoring — CANSLIM (O'Neil) + Value (Buffett/Duan Yongping) + Growth (Peter Lynch). Pure computation, no API calls. |- Financial metrics (财务指标): PE, PB, ROE

| `report.py` | Deep-dive report — 10yr financials, technicals (RSI/MACD/Bollinger), cycle analysis, investment commentary. |

| `market_cycle.py` | Howard Marks 14-dimension cycle assessment using real macro data (GDP/PMI/M2/bonds/FX/margin/IPO/buyback). |### 2. Analysis

| `trading.py` | Multi-dimension trading signals — 4 dimensions (trend/momentum/volume/pattern), signal strength 0-100, fundamental grade A/B/C/D. |- Daily performance summary (每日表现汇总)

| `runner.py` | Cron entry point — morning/midday/close/alert/weekly. Includes China trading calendar (auto-skip holidays). |- Technical signal detection (技术信号检测)

| `notifier.py` | WeChat sender — WeCom webhook, auto-splits messages > 4096 bytes. |- Price alert monitoring (价格预警)

- Sector comparison (板块对比)

## Commands

### 3. Reporting

All commands run from `/home/node/.openclaw/skills/china-stock/`.- Morning briefing at 9:00 AM (早盘简报)

- Market close summary at 3:30 PM (收盘总结)

```bash- Weekly performance report on Saturday (周报)

# Reports

python3 report.py                          # All stocks deep-dive## Usage Examples

python3 report.py --sector 医药            # Specific sector

python3 market_cycle.py                    # Macro cycle analysis### Fetch current watchlist status

python3 market_cycle.py --refresh --send   # Refresh data + send to WeChat```

python3 trading.py                         # Trading signals获取我的自选股行情

python3 trading.py --send                  # Send signals to WeChat```



# Cron runner### Generate daily report

python3 runner.py test                     # Test all components```

python3 runner.py morning                  # Morning brief生成今日股票日报

python3 runner.py weekly                   # Weekly report → WeChat```



# Notifications### Check specific stock

python3 notifier.py --test --channel wecom # Test WeChat```

```查看贵州茅台 600519 的技术分析

```

## Data Access (Python)

### Set price alert

```python```

from stock_data import get_provider设置宁德时代跌破180元时提醒我

p = get_provider()```



# Quotes (Tencent for A-shares with PE/PB, Sina for HK)## Data Sources

quotes = p.get_quotes(['600519', 'hk00700'])- **AKShare**: Primary data source for A-share stocks

- Uses Sina Finance API for real-time quotes

# K-lines (Baostock A-share, AKShare HK)- East Money for news and announcements

df = p.get_history('600519', 120)    # 120 days

# Columns: date, open, high, low, close, volume, amount, pctChg## Notification Channels

- WeCom Bot (企业微信机器人)

# Financials (latest quarter)- ServerChan (Server酱)

fin = p.get_financials('600519')- Telegram (optional)

# Fields: roe, gross_margin, net_margin, revenue_growth, profit_growth

## Configuration

# Multi-year history (A-share 10yr, HK 9yr)Edit `watchlist.json` to customize:

history = p.get_financial_history('600519')- Stock groups (股票分组)

# Returns list of dicts: year, roe, gross_margin, net_margin, revenue_growth, profit_growth, eps- Price alerts (价格预警)

- Index tracking (指数跟踪)

# Macro data (GDP, PMI, M2, bonds, etc.) — used by market_cycle.py

# Uses AKShare: macro_china_gdp, macro_china_pmi, macro_china_money_supply,## Market Hours (A-Share)

#   bond_zh_us_rate, stock_margin_sse, currency_boc_sina, stock_repurchase_em, stock_ipo_info- Morning session: 9:30 - 11:30

- Afternoon session: 13:00 - 15:00

p.cleanup()  # Always call when done (logs out of Baostock)- Trading days: Monday - Friday (excluding holidays)

```

## Notes

## Config Files- Data has 15-minute delay for free tier

- Real-time data available with Tushare Pro subscription

All under `/home/node/.openclaw/stock-data/`:- All times are in China Standard Time (CST/UTC+8)


| File | Purpose |
|------|---------|
| `watchlist.json` | 18 stocks, 6 sectors (白酒/新能源/科技/金融/医药/港股) + price alerts |
| `notifier.json` | WeCom webhook URL |
| `trading-rules.json` | Trading rules (entry/exit/position limits) |
| `market-cycle.json` | Macro cycle manual overrides (optional) |
| `cache/` | Auto-managed data cache (quotes 1min, K-lines 4hr, financials 24hr) |

## Cron Schedule

7 jobs configured in `/home/node/.openclaw/cron/jobs.json`:

| Time | Job |
|------|-----|
| Mon-Fri 09:00 | Morning brief |
| Mon-Fri 09:15 | Trading signals → WeChat |
| Mon-Fri 11:35 | Midday update |
| Mon-Fri 15:05 | Close summary (deep-dive) |
| Mon-Fri */30min | Price alerts |
| Sat 10:00 | Weekly report |
| Biweekly Sat 11:00 | Market cycle analysis |

Daily jobs auto-skip weekends + China public holidays (Sina trading calendar API).

## Stock Codes

- A-shares: 6-digit (e.g., `600519` for 茅台)
- HK stocks: prefix `hk` (e.g., `hk00700` for 腾讯)
- Indices: `000001` (上证), `000300` (沪深300), `399006` (创业板指)

## Dependencies

```
akshare, baostock, pandas, numpy, requests
```
Installed in container via `pip3 install`.

## Notes

- HK stocks: quotes + K-lines + financials all work. No Baostock, uses AKShare instead.
- Index codes: `000xxx` → `sh` (上证), `399xxx` → `sz` (深证). Auto-detected by `stock_data.py`.
- Cache is file-based + in-memory. Second runs complete in < 1 second.
- Long WeChat messages auto-split at section boundaries.
