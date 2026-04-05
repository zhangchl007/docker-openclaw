# China Stock Analysis Skill (中国股票分析技能)

## Overview
This skill collects and analyzes China A-share stock data, generating reports and sending notifications.

## Capabilities

### 1. Data Collection
- Real-time stock quotes (实时行情)
- Daily OHLCV data (日K线数据)
- Technical indicators (技术指标): MA, MACD, RSI, KDJ
- Financial metrics (财务指标): PE, PB, ROE

### 2. Analysis
- Daily performance summary (每日表现汇总)
- Technical signal detection (技术信号检测)
- Price alert monitoring (价格预警)
- Sector comparison (板块对比)

### 3. Reporting
- Morning briefing at 9:00 AM (早盘简报)
- Market close summary at 3:30 PM (收盘总结)
- Weekly performance report on Saturday (周报)

## Usage Examples

### Fetch current watchlist status
```
获取我的自选股行情
```

### Generate daily report
```
生成今日股票日报
```

### Check specific stock
```
查看贵州茅台 600519 的技术分析
```

### Set price alert
```
设置宁德时代跌破180元时提醒我
```

## Data Sources
- **AKShare**: Primary data source for A-share stocks
- Uses Sina Finance API for real-time quotes
- East Money for news and announcements

## Notification Channels
- WeCom Bot (企业微信机器人)
- ServerChan (Server酱)
- Telegram (optional)

## Configuration
Edit `watchlist.json` to customize:
- Stock groups (股票分组)
- Price alerts (价格预警)
- Index tracking (指数跟踪)

## Market Hours (A-Share)
- Morning session: 9:30 - 11:30
- Afternoon session: 13:00 - 15:00
- Trading days: Monday - Friday (excluding holidays)

## Notes
- Data has 15-minute delay for free tier
- Real-time data available with Tushare Pro subscription
- All times are in China Standard Time (CST/UTC+8)
