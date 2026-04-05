# OpenClaw China Stock Analysis System

## 📋 Requirements Document

### 1. Project Overview

Build an automated China stock analysis system using OpenClaw that:
- Collects real-time and historical stock data for a customizable watchlist
- Analyzes stock performance, trends, and news
- Generates daily/weekly summary reports
- Sends notifications via WeChat

### 2. System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        OpenClaw Gateway                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │
│  │ Cron Jobs   │  │ Stock Skill │  │ Analysis    │  │ WeChat      │ │
│  │ (Scheduler) │→ │ (Collector) │→ │ Engine      │→ │ Channel     │ │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
         │                  │                               │
         ▼                  ▼                               ▼
┌─────────────────┐ ┌─────────────────┐           ┌─────────────────┐
│ Schedule Config │ │ Stock Data APIs │           │ WeChat Work API │
│ (cron expressions)│ │ - AKShare      │           │ or WeCom Bot    │
│                 │ │ - Tushare       │           │                 │
│                 │ │ - East Money    │           │                 │
└─────────────────┘ └─────────────────┘           └─────────────────┘
```

### 3. Data Sources for China Stocks

| Source | Type | Features | API |
|--------|------|----------|-----|
| **AKShare** | Free | A-shares, HK, US stocks | Python package |
| **Tushare** | Freemium | Professional A-share data | REST API |
| **East Money (东方财富)** | Free | Real-time quotes, news | Web scraping |
| **Sina Finance** | Free | Real-time quotes | REST API |
| **10jqka (同花顺)** | Free | Technical analysis | Web scraping |

### 4. Notification Channels

Since WeChat personal API is restricted, we have these alternatives:

| Channel | Difficulty | Features |
|---------|------------|----------|
| **WeCom (企业微信)** | Easy | Official API, group bots |
| **Server酱 (ServerChan)** | Easy | Push to WeChat via webhook |
| **PushPlus** | Easy | WeChat push service |
| **Telegram** | Easy | Full bot API support |
| **Email** | Easy | Fallback option |

### 5. Functional Requirements

#### 5.1 Stock Data Collection
- [ ] Support A-share stock codes (e.g., 600519, 000858)
- [ ] Real-time price quotes
- [ ] Daily OHLCV (Open, High, Low, Close, Volume)
- [ ] Technical indicators (MA, MACD, RSI, KDJ)
- [ ] Financial metrics (PE, PB, ROE)
- [ ] News and announcements

#### 5.2 Watchlist Management
- [ ] Add/remove stocks from watchlist
- [ ] Group stocks by category (e.g., "白酒", "新能源", "科技")
- [ ] Set price alerts
- [ ] Custom analysis rules per stock

#### 5.3 Analysis Features
- [ ] Daily price change summary
- [ ] Technical signal detection
- [ ] Sector rotation analysis
- [ ] Volume anomaly detection
- [ ] News sentiment analysis
- [ ] Comparison with indices (上证, 深证, 创业板)

#### 5.4 Notification System
- [ ] Morning briefing (9:00 AM)
- [ ] Market close summary (3:30 PM)
- [ ] Real-time alerts for significant events
- [ ] Weekly performance report (Saturday)

### 6. Technical Requirements

#### 6.1 OpenClaw Configuration
```json
{
  "skills": {
    "china-stock": {
      "enabled": true,
      "dataSource": "akshare",
      "cacheDir": "/home/node/.openclaw/stock-cache"
    }
  },
  "cron": {
    "stock-morning-brief": "0 9 * * 1-5",
    "stock-close-summary": "30 15 * * 1-5",
    "stock-weekly-report": "0 10 * * 6"
  }
}
```

#### 6.2 Dependencies
- Python 3.9+ (for AKShare)
- Node.js 18+ (OpenClaw runtime)
- SQLite (data caching)
- Redis (optional, for real-time alerts)

### 7. File Structure

```
openclaw-docker/
├── docker-compose.yml
├── data/
│   ├── openclaw.json           # Main config
│   ├── skills/
│   │   └── china-stock/        # Custom stock skill
│   │       ├── skill.json      # Skill manifest
│   │       ├── SKILL.md        # Skill instructions
│   │       ├── collector.py    # Data collection script
│   │       ├── analyzer.py     # Analysis engine
│   │       └── notifier.py     # Notification handler
│   ├── stock-data/
│   │   ├── watchlist.json      # Stock watchlist
│   │   ├── cache/              # Data cache
│   │   └── reports/            # Generated reports
│   └── canvas/
│       └── stock-dashboard/    # Web dashboard (optional)
├── scripts/
│   ├── setup-akshare.sh        # Install AKShare
│   └── test-notification.sh    # Test WeChat push
└── config/
    └── wecom-bot.json.example  # WeChat bot config example
```

### 8. Sample Watchlist

```json
{
  "version": 1,
  "groups": {
    "白酒": ["600519", "000858", "000568"],
    "新能源": ["300750", "002594", "600438"],
    "科技": ["002415", "300059", "002230"],
    "金融": ["601318", "600036", "601166"]
  },
  "alerts": {
    "600519": {
      "priceAbove": 1900,
      "priceBelow": 1600,
      "changePercent": 5
    }
  },
  "indices": ["000001", "399001", "399006"]
}
```

### 9. Sample Daily Report Format

```markdown
# 📊 股票日报 - 2026-04-05

## 📈 今日概览
- 上证指数: 3,256.78 (+1.23%)
- 深证成指: 10,892.45 (+0.89%)
- 创业板指: 2,156.32 (+1.56%)

## 🔥 自选股表现

### 涨幅榜
| 股票 | 代码 | 现价 | 涨跌幅 |
|------|------|------|--------|
| 贵州茅台 | 600519 | ¥1,856.00 | +2.34% |
| 宁德时代 | 300750 | ¥198.50 | +1.89% |

### 跌幅榜
| 股票 | 代码 | 现价 | 涨跌幅 |
|------|------|------|--------|
| 比亚迪 | 002594 | ¥256.30 | -1.23% |

## 📡 技术信号
- 🟢 **600519** MACD金叉，建议关注
- 🟡 **300750** RSI接近超买区域
- 🔴 **002594** 跌破5日均线

## 📰 重要新闻
1. 贵州茅台发布Q1财报，营收超预期
2. 宁德时代获得新能源汽车大单

---
*由 OpenClaw 自动生成 | 数据来源: AKShare*
```

### 10. Implementation Phases

#### Phase 1: Basic Setup (Week 1)
- [ ] Configure OpenClaw environment
- [ ] Set up WeChat notification channel
- [ ] Create basic stock data collector
- [ ] Test manual data fetch

#### Phase 2: Automation (Week 2)
- [ ] Implement cron jobs for scheduling
- [ ] Build analysis engine
- [ ] Create report templates
- [ ] Test automated reports

#### Phase 3: Enhancement (Week 3)
- [ ] Add technical indicators
- [ ] Implement price alerts
- [ ] Build web dashboard (optional)
- [ ] Add news aggregation

#### Phase 4: Optimization (Week 4)
- [ ] Performance tuning
- [ ] Error handling
- [ ] Logging and monitoring
- [ ] Documentation

---

## 🚀 Next Steps

1. **Set up notification channel** - Choose WeCom Bot or ServerChan
2. **Install AKShare** - For China stock data
3. **Create custom skill** - Stock analysis skill
4. **Configure cron jobs** - Scheduled reports
5. **Test end-to-end** - Verify the complete flow
