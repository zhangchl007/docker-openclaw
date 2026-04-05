# OpenClaw Stock Analysis System - Requirements Document

## 🎯 Project Vision

Build an **intelligent stock analysis system** that combines:
- **Duan Yongping's** value investing principles (business moats, management quality)
- **Peter Lynch's** growth stock methodology (PEG, stock categories)
- **William O'Neil's** CANSLIM system (momentum, institutional support)

The system automatically collects data, performs multi-dimensional analysis, and delivers actionable insights via WeChat.

---

## 📊 System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        OpenClaw Gateway                                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │
│  │   Cron      │  │   Data      │  │  Analysis   │  │  WeChat     │   │
│  │  Scheduler  │→ │  Collector  │→ │   Engine    │→ │  Notifier   │   │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘   │
│                          │                │                             │
│                          ▼                ▼                             │
│                   ┌─────────────┐  ┌─────────────┐                     │
│                   │  Database   │  │   Report    │                     │
│                   │  (SQLite)   │  │  Generator  │                     │
│                   └─────────────┘  └─────────────┘                     │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   AKShare    │    │   Tushare    │    │  East Money  │
│  (Free API)  │    │  (Pro API)   │    │  (Scraping)  │
└──────────────┘    └──────────────┘    └──────────────┘
```

---

## 📋 Functional Requirements

### 1. Data Collection Module

#### 1.1 Market Data
| Data Type | Source | Frequency | Storage |
|-----------|--------|-----------|---------|
| Real-time Quotes | AKShare | Every 30 min | Memory/Cache |
| Daily OHLCV | AKShare | Daily 15:30 | SQLite |
| Index Data | AKShare | Real-time | Memory |
| Northbound Flow | East Money | Daily | SQLite |

#### 1.2 Fundamental Data
| Data Type | Source | Frequency | Storage |
|-----------|--------|-----------|---------|
| Financial Statements | AKShare/Tushare | Quarterly | SQLite |
| PE/PB/ROE | AKShare | Daily | SQLite |
| Earnings Growth | Calculated | Quarterly | SQLite |
| Free Cash Flow | Calculated | Quarterly | SQLite |

#### 1.3 Institutional Data
| Data Type | Source | Frequency | Storage |
|-----------|--------|-----------|---------|
| Mutual Fund Holdings | East Money | Quarterly | SQLite |
| Shareholder Count | AKShare | Quarterly | SQLite |
| Insider Trading | AKShare | As announced | SQLite |
| Northbound Holdings | East Money | Daily | SQLite |

### 2. Analysis Engine

#### 2.1 CANSLIM Scoring System
```python
class CANSLIMAnalyzer:
    """
    Score each stock on 0-100 scale based on CANSLIM criteria
    """
    
    def score_current_earnings(self, stock) -> int:
        """C - Current quarterly EPS growth"""
        # 25%+ growth = 20 points
        # 50%+ growth = 25 points (max)
        
    def score_annual_earnings(self, stock) -> int:
        """A - Annual earnings growth over 3-5 years"""
        # 25%+ CAGR = 20 points
        # Acceleration = bonus points
        
    def score_new_factor(self, stock) -> int:
        """N - New products, management, or price highs"""
        # 52-week high = 10 points
        # New product launches = 5 points
        
    def score_supply_demand(self, stock) -> int:
        """S - Supply and demand (volume analysis)"""
        # Volume surge on up days = 15 points
        # Small float = bonus
        
    def score_leader(self, stock) -> int:
        """L - Leader or laggard (relative strength)"""
        # RS > 80 = 15 points
        # RS > 90 = 20 points (max)
        
    def score_institutional(self, stock) -> int:
        """I - Institutional sponsorship"""
        # Increasing fund holdings = 10 points
        # Quality institutions = bonus
        
    def score_market(self) -> int:
        """M - Market direction"""
        # Uptrend = 10 points
        # Downtrend = 0 points
```

#### 2.2 Value Investing Metrics (Duan Yongping Style)
```python
class ValueAnalyzer:
    """
    Evaluate business quality and intrinsic value
    """
    
    def analyze_moat(self, stock) -> dict:
        """Assess competitive moat strength"""
        return {
            'brand_power': self._score_brand(),
            'switching_cost': self._score_switching_cost(),
            'network_effect': self._score_network_effect(),
            'cost_advantage': self._score_cost_advantage(),
            'intangibles': self._score_patents_licenses(),
            'overall_moat': self._calculate_overall_moat()
        }
    
    def analyze_management(self, stock) -> dict:
        """Evaluate management quality"""
        return {
            'ownership': self._insider_ownership(),
            'track_record': self._promises_kept(),
            'capital_allocation': self._roic_trend(),
            'compensation': self._exec_pay_vs_performance()
        }
    
    def calculate_intrinsic_value(self, stock) -> float:
        """DCF-based intrinsic value estimation"""
        fcf = self._get_free_cash_flow(stock)
        growth_rate = self._estimate_growth(stock)
        discount_rate = self._calculate_wacc(stock)
        return self._dcf_model(fcf, growth_rate, discount_rate)
```

#### 2.3 Growth Stock Analysis (Peter Lynch Style)
```python
class GrowthAnalyzer:
    """
    Categorize and analyze growth stocks
    """
    
    def categorize_stock(self, stock) -> str:
        """Classify into Lynch's 6 categories"""
        growth_rate = self._get_earnings_growth(stock)
        dividend_yield = self._get_dividend_yield(stock)
        
        if growth_rate < 5:
            return "SLOW_GROWER"
        elif 10 <= growth_rate <= 15:
            return "STALWART"
        elif growth_rate > 20:
            return "FAST_GROWER"
        elif self._is_cyclical(stock):
            return "CYCLICAL"
        elif self._is_turnaround(stock):
            return "TURNAROUND"
        elif self._has_hidden_assets(stock):
            return "ASSET_PLAY"
    
    def calculate_peg(self, stock) -> float:
        """PEG = PE / Growth Rate"""
        pe = self._get_pe_ratio(stock)
        growth = self._get_earnings_growth(stock)
        return pe / growth if growth > 0 else float('inf')
    
    def lynch_score(self, stock) -> dict:
        """Overall Lynch-style evaluation"""
        return {
            'category': self.categorize_stock(stock),
            'peg_ratio': self.calculate_peg(stock),
            'peg_signal': 'UNDERVALUED' if self.calculate_peg(stock) < 1 else 'FAIRLY_VALUED',
            'growth_quality': self._evaluate_growth_quality(stock),
            'story_strength': self._evaluate_business_story(stock)
        }
```

### 3. Report Generation

#### 3.1 Daily Report
```
📊 Daily Market Summary - {date}

MARKET OVERVIEW
- SSE Index: {price} ({change}%)
- Market Direction: {bullish/bearish/neutral}

PORTFOLIO ALERTS
- {stock}: {alert_type} - {message}

NORTHBOUND FLOW
- Net Flow: {amount}
- Top Buys: {stocks}
- Top Sells: {stocks}

WATCHLIST MOVERS
| Stock | Price | Change | Volume | Signal |
|-------|-------|--------|--------|--------|
```

#### 3.2 Weekly Report
```
📈 Weekly Investment Report - Week {n}

PORTFOLIO PERFORMANCE
- Total Return: {%}
- vs Index: {outperform/underperform}

CANSLIM RANKINGS (Top 10)
| Rank | Stock | C | A | N | S | L | I | M | Total |
|------|-------|---|---|---|---|---|---|---|-------|

FUNDAMENTAL CHANGES
- {stock}: {earnings_revision/guidance_change}

INSTITUTIONAL ACTIVITY
- Smart Money Buys: {stocks}
- Smart Money Sells: {stocks}

TECHNICAL SIGNALS
- Breakouts: {stocks}
- Breakdowns: {stocks}

INVESTMENT THESIS UPDATES
- {stock}: {thesis_status}
```

#### 3.3 Deep Dive Report (Per Stock)
```
🔬 Deep Dive: {stock_name} ({code})

EXECUTIVE SUMMARY
{one_paragraph_summary}

BUSINESS MODEL
- What they do: {description}
- How they make money: {revenue_model}
- Competitive position: {market_share, ranking}

MOAT ANALYSIS (Duan Yongping Framework)
| Moat Type | Score | Evidence |
|-----------|-------|----------|
| Brand | {1-5} | {evidence} |
| Switching Cost | {1-5} | {evidence} |
| Network Effect | {1-5} | {evidence} |
| Cost Advantage | {1-5} | {evidence} |
| Overall Moat | {1-5} | {conclusion} |

GROWTH ANALYSIS (Peter Lynch Framework)
- Category: {slow_grower/stalwart/fast_grower/...}
- PEG Ratio: {value} ({undervalued/fair/overvalued})
- Growth Quality: {score}
- 3-Year Revenue CAGR: {%}
- 3-Year Earnings CAGR: {%}

CANSLIM SCORE: {total}/100
| C | A | N | S | L | I | M |
|---|---|---|---|---|---|---|
|{s}|{s}|{s}|{s}|{s}|{s}|{s}|

MANAGEMENT ASSESSMENT
- Insider Ownership: {%}
- Track Record: {rating}
- Capital Allocation: {rating}

VALUATION
- Current PE: {value} vs Historical: {range}
- PB: {value}, ROE: {%}
- Intrinsic Value (DCF): {value}
- Margin of Safety: {%}

RISKS
1. {risk_1}
2. {risk_2}
3. {risk_3}

INVESTMENT THESIS
{2-3_paragraph_thesis}

ACTION RECOMMENDATION
{BUY/HOLD/SELL} at {price_range}
```

### 4. Alert System

#### 4.1 Price Alerts
- Price above/below threshold
- Percentage change exceeds limit
- 52-week high/low reached

#### 4.2 Fundamental Alerts
- Earnings announcement
- Guidance revision
- Insider trading
- Analyst rating change

#### 4.3 Technical Alerts
- Volume surge (>2x average)
- Moving average crossover
- RSI overbought/oversold
- Support/Resistance breach

#### 4.4 CANSLIM Alerts
- RS Rating improvement/decline
- Institutional ownership change
- Market direction change

---

## 🗄️ Data Model

### Database Schema (SQLite)

```sql
-- Stock Master
CREATE TABLE stocks (
    code TEXT PRIMARY KEY,
    name TEXT,
    market TEXT,
    industry TEXT,
    sector TEXT,
    list_date DATE,
    updated_at TIMESTAMP
);

-- Daily Prices
CREATE TABLE daily_prices (
    code TEXT,
    date DATE,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume INTEGER,
    amount REAL,
    PRIMARY KEY (code, date)
);

-- Financial Statements (Quarterly)
CREATE TABLE financials (
    code TEXT,
    period TEXT,  -- e.g., '2026Q1'
    revenue REAL,
    net_profit REAL,
    eps REAL,
    roe REAL,
    debt_ratio REAL,
    free_cash_flow REAL,
    PRIMARY KEY (code, period)
);

-- CANSLIM Scores
CREATE TABLE canslim_scores (
    code TEXT,
    date DATE,
    c_score INTEGER,
    a_score INTEGER,
    n_score INTEGER,
    s_score INTEGER,
    l_score INTEGER,
    i_score INTEGER,
    m_score INTEGER,
    total_score INTEGER,
    PRIMARY KEY (code, date)
);

-- Watchlist
CREATE TABLE watchlist (
    code TEXT PRIMARY KEY,
    group_name TEXT,
    added_date DATE,
    buy_thesis TEXT,
    target_price REAL,
    stop_loss REAL
);

-- Alerts
CREATE TABLE alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT,
    alert_type TEXT,
    condition TEXT,
    threshold REAL,
    triggered_at TIMESTAMP,
    message TEXT
);

-- Investment Journal
CREATE TABLE journal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT,
    date DATE,
    entry_type TEXT,  -- 'BUY', 'SELL', 'NOTE', 'THESIS_UPDATE'
    content TEXT,
    price REAL
);
```

---

## 📅 Scheduled Tasks

| Task | Schedule | Description |
|------|----------|-------------|
| `daily_data_sync` | 09:00, 15:30 | Sync daily price data |
| `morning_brief` | 09:00 Mon-Fri | Market preview |
| `midday_update` | 11:35 Mon-Fri | Mid-session summary |
| `close_summary` | 15:05 Mon-Fri | Daily closing report |
| `price_alert_check` | */30 9-15 Mon-Fri | Check price alerts |
| `weekly_report` | 10:00 Saturday | Weekly analysis |
| `fundamental_update` | 20:00 Daily | Update fundamentals |
| `canslim_scoring` | 21:00 Daily | Calculate CANSLIM scores |
| `institutional_update` | 08:00 Monthly | Update institutional data |

---

## 🔌 API Requirements

### Required Data Sources

1. **AKShare** (Primary - Free)
   - Real-time quotes
   - Historical prices
   - Basic financials
   - Index data

2. **Tushare Pro** (Optional - Paid)
   - Higher quality fundamentals
   - Analyst estimates
   - Detailed financials

3. **East Money API** (Supplementary)
   - Northbound flow
   - Fund holdings
   - News feed

### WeChat Integration
- WeCom Bot (current)
- WeCom Application API (optional, more secure)

---

## 📁 Project Structure

```
data/skills/china-stock/
├── skill.json              # Skill manifest
├── SKILL.md                # Skill documentation
├── requirements.txt        # Python dependencies
│
├── core/
│   ├── __init__.py
│   ├── database.py         # SQLite operations
│   ├── config.py           # Configuration management
│   └── utils.py            # Utility functions
│
├── collectors/
│   ├── __init__.py
│   ├── akshare_collector.py    # AKShare data
│   ├── tushare_collector.py    # Tushare data (optional)
│   └── eastmoney_collector.py  # East Money data
│
├── analyzers/
│   ├── __init__.py
│   ├── canslim.py          # CANSLIM scoring
│   ├── value.py            # Value investing analysis
│   ├── growth.py           # Growth stock analysis
│   ├── technical.py        # Technical indicators
│   └── composite.py        # Combined analysis
│
├── reporters/
│   ├── __init__.py
│   ├── daily.py            # Daily report generator
│   ├── weekly.py           # Weekly report generator
│   ├── deep_dive.py        # Stock deep dive report
│   └── templates/          # Report templates
│
├── alerts/
│   ├── __init__.py
│   ├── price_alerts.py     # Price monitoring
│   ├── fundamental_alerts.py
│   └── technical_alerts.py
│
├── notifiers/
│   ├── __init__.py
│   ├── wecom.py            # WeCom integration
│   └── base.py             # Base notifier class
│
├── runner.py               # Main entry point
├── setup.py                # Setup script
└── tests/
    ├── test_collectors.py
    ├── test_analyzers.py
    └── test_reporters.py
```

---

## 🚀 Implementation Phases

### Phase 1: Foundation (Week 1-2)
- [ ] Set up database schema
- [ ] Implement basic data collectors
- [ ] Create daily price sync
- [ ] Basic daily report

### Phase 2: Analysis Engine (Week 3-4)
- [ ] CANSLIM scoring system
- [ ] PEG calculation
- [ ] Basic technical indicators
- [ ] Composite scoring

### Phase 3: Advanced Analysis (Week 5-6)
- [ ] Moat analysis framework
- [ ] Management assessment
- [ ] DCF valuation model
- [ ] Growth quality metrics

### Phase 4: Reporting (Week 7-8)
- [ ] Weekly report generation
- [ ] Deep dive reports
- [ ] Alert system
- [ ] Investment journal

### Phase 5: Optimization (Week 9-10)
- [ ] Performance tuning
- [ ] Error handling
- [ ] Backtesting framework
- [ ] Documentation

---

## 📊 Success Metrics

1. **Data Quality**
   - 99%+ uptime for data collection
   - < 15 min data delay

2. **Analysis Accuracy**
   - CANSLIM scores correlate with performance
   - PEG signals validated by returns

3. **User Experience**
   - Reports delivered on schedule
   - Actionable insights in every report

4. **Investment Performance**
   - Track record vs benchmark
   - Risk-adjusted returns

---

## ⚠️ Risk Considerations

1. **Data Source Risks**
   - API rate limits
   - Data quality issues
   - Source discontinuation

2. **Analysis Limitations**
   - Models are not predictive
   - Past performance ≠ future results
   - Qualitative factors hard to quantify

3. **Technical Risks**
   - System downtime
   - Network connectivity
   - WeChat API changes

---

*Document Version: 2.0*
*Last Updated: 2026-04-05*
