#!/usr/bin/env python3
"""
Stock Data Provider - Direct API Access

直接调用新浪/腾讯 API，不依赖 AKShare 的东方财富接口。
只获取 watchlist 里的股票，不下载全市场数据。

数据源：
1. 新浪财经 - 实时行情 (最快, 0.7秒/4只股票)
2. 腾讯财经 - 实时行情 (备用)
3. Baostock - 历史K线和财务数据
"""

import json
import re
import hashlib
import time
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict

import requests
import pandas as pd

try:
    import baostock as bs
    BAOSTOCK_AVAILABLE = True
except ImportError:
    BAOSTOCK_AVAILABLE = False


def parse_watchlist(wl: Dict) -> Dict[str, List[Dict]]:
    """Parse watchlist v1 (groups) or v2 (sectors) format.
    Returns: {sector_name: [{'code':..., 'name':..., ...}, ...]}
    """
    # v2 format: sectors with industry metadata
    if 'sectors' in wl:
        result = {}
        for name, sector in wl['sectors'].items():
            stocks = sector.get('stocks', [])
            # Attach sector metadata to each stock
            for s in stocks:
                s['_sector'] = name
                s['_industry'] = sector.get('industry', '')
                s['_cycle_type'] = sector.get('cycle_type', '')
            result[name] = stocks
        return result
    # v1 format: simple groups
    return wl.get('groups', {})


@dataclass
class StockQuote:
    """实时行情"""
    code: str
    name: str = ""
    price: float = 0.0
    change: float = 0.0
    change_pct: float = 0.0
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    prev_close: float = 0.0
    volume: float = 0.0
    amount: float = 0.0
    pe: float = 0.0
    pb: float = 0.0
    timestamp: str = ""


@dataclass
class StockFinancials:
    """财务数据 (最新一期)"""
    code: str
    roe: float = 0.0
    gross_margin: float = 0.0
    net_margin: float = 0.0
    revenue_growth: float = 0.0
    profit_growth: float = 0.0
    debt_ratio: float = 0.0
    current_ratio: float = 0.0
    # 银行专属指标
    roa: float = 0.0           # 总资产利润率 (银行约1%为正常)
    dividend_yield: float = 0.0 # 股息率
    timestamp: str = ""


@dataclass
class YearlyFinancials:
    """单年度财务数据"""
    year: str
    roe: float = 0.0
    gross_margin: float = 0.0
    net_margin: float = 0.0
    revenue_growth: float = 0.0
    profit_growth: float = 0.0
    revenue: float = 0.0       # 亿元
    net_profit: float = 0.0    # 亿元
    eps: float = 0.0
    roic: float = 0.0
    debt_ratio: float = 0.0
    current_ratio: float = 0.0
    roa: float = 0.0           # 总资产利润率


class SimpleCache:
    """简单缓存"""
    
    def __init__(self, cache_dir: str = "/home/node/.openclaw/stock-data/cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._mem: Dict[str, tuple] = {}
    
    def _path(self, key: str) -> Path:
        return self.cache_dir / f"{hashlib.md5(key.encode()).hexdigest()[:12]}.json"
    
    def get(self, key: str, ttl_min: int = 60) -> Optional[Any]:
        if key in self._mem:
            data, ts = self._mem[key]
            if time.time() - ts < ttl_min * 60:
                return data
        
        path = self._path(key)
        if path.exists():
            try:
                with open(path) as f:
                    cached = json.load(f)
                ts = datetime.fromisoformat(cached['ts'])
                if datetime.now() - ts < timedelta(minutes=ttl_min):
                    self._mem[key] = (cached['data'], ts.timestamp())
                    return cached['data']
            except:
                pass
        return None
    
    def set(self, key: str, data: Any):
        self._mem[key] = (data, time.time())
        try:
            with open(self._path(key), 'w') as f:
                json.dump({'ts': datetime.now().isoformat(), 'data': data}, f)
        except:
            pass


class SinaAPI:
    """新浪财经实时行情 - 支持A股+港股"""
    
    @staticmethod
    def _format_code(code: str) -> str:
        """格式化代码: 600519->sh600519, hk00700->hk00700"""
        if code.startswith('hk'):
            return code  # 港股直接用
        c = str(code).zfill(6)
        return f"sh{c}" if c.startswith('6') else f"sz{c}"
    
    @staticmethod
    def get_quotes(codes: List[str]) -> Dict[str, StockQuote]:
        if not codes:
            return {}
        
        sina_codes = [SinaAPI._format_code(c) for c in codes]
        url = f"http://hq.sinajs.cn/list={','.join(sina_codes)}"
        headers = {'Referer': 'https://finance.sina.com.cn/'}
        
        try:
            r = requests.get(url, headers=headers, timeout=10)
            r.encoding = 'gbk'
            return SinaAPI._parse(r.text)
        except Exception as e:
            print(f"[Sina] Error: {e}")
            return {}
    
    @staticmethod
    def _parse(text: str) -> Dict[str, StockQuote]:
        results = {}
        for line in text.strip().split('\n'):
            match = re.match(r'var hq_str_(\w+)="(.*)";?', line)
            if not match or not match.group(2):
                continue
            
            sina_code = match.group(1)  # e.g. sh600519 or hk00700
            parts = match.group(2).split(',')
            
            # Detect HK stock (different format)
            if sina_code.startswith('hk'):
                code = sina_code  # Keep hk00700 as code
                if len(parts) < 10:
                    continue
                try:
                    q = StockQuote(
                        code=code,
                        name=parts[1],
                        price=float(parts[6] or 0),
                        prev_close=float(parts[3] or 0),
                        open=float(parts[2] or 0),
                        high=float(parts[4] or 0),
                        low=float(parts[5] or 0),
                        volume=float(parts[12] or 0),
                        amount=float(parts[11] or 0),
                        change=float(parts[7] or 0),
                        change_pct=float(parts[8] or 0),
                        timestamp=parts[17] if len(parts) > 17 else ""
                    )
                    results[code] = q
                except:
                    pass
            else:
                # A-share format
                code = sina_code[2:]  # sh600519 -> 600519
                if len(parts) < 32:
                    continue
                try:
                    q = StockQuote(
                        code=code,
                        name=parts[0],
                        open=float(parts[1] or 0),
                        prev_close=float(parts[2] or 0),
                        price=float(parts[3] or 0),
                        high=float(parts[4] or 0),
                        low=float(parts[5] or 0),
                        volume=float(parts[8] or 0),
                        amount=float(parts[9] or 0),
                        timestamp=f"{parts[30]} {parts[31]}"
                    )
                    if q.prev_close > 0:
                        q.change = q.price - q.prev_close
                        q.change_pct = (q.change / q.prev_close) * 100
                    results[code] = q
                except:
                    pass
        return results


class TencentAPI:
    """腾讯财经 API - 提供 PE/PB 数据 (仅A股)"""
    
    @staticmethod
    def get_quotes(codes: List[str]) -> Dict[str, StockQuote]:
        # Filter out HK stocks (Tencent API format is different for HK)
        a_codes = [c for c in codes if not str(c).startswith('hk')]
        if not a_codes:
            return {}
        
        qq_codes = []
        for c in a_codes:
            c = str(c).zfill(6)
            qq_codes.append(f"sh{c}" if c.startswith('6') else f"sz{c}")
        
        url = f"http://qt.gtimg.cn/q={','.join(qq_codes)}"
        
        try:
            r = requests.get(url, timeout=10)
            r.encoding = 'gbk'
            return TencentAPI._parse(r.text)
        except Exception as e:
            print(f"[Tencent] Error: {e}")
            return {}
    
    @staticmethod
    def _parse(text: str) -> Dict[str, StockQuote]:
        results = {}
        for line in text.strip().split('\n'):
            match = re.match(r'v_(\w+)="(.*)";?', line)
            if not match or not match.group(2):
                continue
            
            code = match.group(1)[2:]  # sh600519 -> 600519
            parts = match.group(2).split('~')
            if len(parts) < 45:
                continue
            
            try:
                q = StockQuote(
                    code=code,
                    name=parts[1],
                    price=float(parts[3] or 0),
                    prev_close=float(parts[4] or 0),
                    open=float(parts[5] or 0),
                    volume=float(parts[6] or 0) * 100,       # 手 -> 股
                    amount=float(parts[37] or 0) * 10000,     # 万 -> 元
                    high=float(parts[33] or 0),
                    low=float(parts[34] or 0),
                    change=float(parts[31] or 0),
                    change_pct=float(parts[32] or 0),
                    pe=float(parts[39] or 0),
                    pb=float(parts[46] or 0) if len(parts) > 46 else 0,
                    timestamp=parts[30] if len(parts) > 30 else ""
                )
                results[code] = q
            except:
                pass
        return results


class HKStockAPI:
    """港股历史数据 - 使用AKShare新浪源"""
    
    @staticmethod
    def get_history(code: str, days: int = 120) -> pd.DataFrame:
        """获取港股日K线历史 (code格式: hk00700 -> 00700)"""
        try:
            import akshare as ak
            symbol = code.replace('hk', '')  # hk00700 -> 00700
            df = ak.stock_hk_daily(symbol=symbol, adjust='qfq')
            if df.empty:
                return df
            
            # 只取最近N天
            df['date'] = pd.to_datetime(df['date'])
            cutoff = datetime.now() - timedelta(days=days)
            df = df[df['date'] >= cutoff].copy()
            df['date'] = df['date'].dt.strftime('%Y-%m-%d')
            
            # 计算涨跌幅
            df['pctChg'] = df['close'].pct_change() * 100
            
            # Convert types
            for col in ['open', 'high', 'low', 'close', 'volume', 'amount']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            return df.reset_index(drop=True)
        except Exception as e:
            print(f"[HK] History error {code}: {e}")
            return pd.DataFrame()


class FinancialHistoryAPI:
    """多年财务数据 - A股用同花顺, 港股用东方财富"""

    @staticmethod
    def _parse_cn_number(s: str) -> float:
        """解析中文数字: '1.23亿' -> 1.23, '3170.93万' -> 0.317093"""
        if not s or s == 'False' or s is False:
            return 0
        s = str(s).strip()
        try:
            if '亿' in s:
                return float(s.replace('亿', ''))
            elif '万' in s:
                return float(s.replace('万', '')) / 10000
            elif '%' in s:
                return float(s.replace('%', ''))
            else:
                return float(s)
        except:
            return 0

    @staticmethod
    def _parse_pct(s) -> float:
        """解析百分比: '12.34%' -> 12.34, '306.48%' -> 306.48"""
        if not s or s == 'False' or s is False:
            return 0
        try:
            return float(str(s).replace('%', ''))
        except:
            return 0

    @classmethod
    def get_hk_history(cls, code: str, years: int = 5) -> List[Dict]:
        """港股多年财务 via 东方财富"""
        try:
            import akshare as ak
            symbol = code.replace('hk', '')  # hk00700 -> 00700
            df = ak.stock_financial_hk_analysis_indicator_em(symbol=symbol)
            if df.empty:
                return []

            result = []
            for _, row in df.head(years).iterrows():
                result.append(asdict(YearlyFinancials(
                    year=str(row.get('REPORT_DATE', ''))[:10],
                    roe=float(row.get('ROE_AVG', 0) or 0),
                    gross_margin=float(row.get('GROSS_PROFIT_RATIO', 0) or 0),
                    net_margin=float(row.get('NET_PROFIT_RATIO', 0) or 0),
                    revenue_growth=float(row.get('OPERATE_INCOME_YOY', 0) or 0),
                    profit_growth=float(row.get('HOLDER_PROFIT_YOY', 0) or 0),
                    revenue=float(row.get('OPERATE_INCOME', 0) or 0) / 1e8,
                    net_profit=float(row.get('HOLDER_PROFIT', 0) or 0) / 1e8,
                    eps=float(row.get('BASIC_EPS', 0) or 0),
                    roic=float(row.get('ROIC_YEARLY', 0) or 0),
                    debt_ratio=float(row.get('DEBT_ASSET_RATIO', 0) or 0),
                    current_ratio=float(row.get('CURRENT_RATIO', 0) or 0),
                )))
            return result
        except Exception as e:
            print(f"[Finance] HK history error {code}: {e}")
            return []

    @classmethod
    def get_a_share_history(cls, code: str, years: int = 5) -> List[Dict]:
        """A股多年财务 via 同花顺 + 银行ROA补充"""
        try:
            import akshare as ak
            df = ak.stock_financial_abstract_ths(symbol=code)
            if df.empty:
                return []

            # Only keep annual reports (12-31), sorted newest first
            annual = df[df['报告期'].astype(str).str.endswith('12-31')].copy()
            annual = annual.sort_values('报告期', ascending=False).head(years)

            # Check if this is a bank/financial stock (gross margin = 0)
            is_bank = False
            for _, row in annual.head(1).iterrows():
                gm = cls._parse_pct(row.get('销售毛利率', 0))
                if gm == 0:
                    is_bank = True

            # ROA only for banks (no gross margin)
            roa_map = {}
            if is_bank:
                try:
                    start_yr = str(int(annual['报告期'].iloc[-1][:4]) - 1) if len(annual) > 0 else '2015'
                    df_ind = ak.stock_financial_analysis_indicator(symbol=code, start_year=start_yr)
                    if not df_ind.empty:
                        annual_ind = df_ind[df_ind['日期'].astype(str).str.endswith('-12-31')]
                        for _, r in annual_ind.iterrows():
                            yr = str(r['日期'])[:10]
                            roa_map[yr] = float(r.get('总资产利润率(%)', 0) or 0)
                except:
                    pass

            result = []
            for _, row in annual.iterrows():
                yr = str(row.get('报告期', ''))[:10]
                result.append(asdict(YearlyFinancials(
                    year=yr,
                    roe=cls._parse_pct(row.get('净资产收益率', 0)),
                    gross_margin=cls._parse_pct(row.get('销售毛利率', 0)),
                    net_margin=cls._parse_pct(row.get('销售净利率', 0)),
                    revenue_growth=cls._parse_pct(row.get('营业总收入同比增长率', 0)),
                    profit_growth=cls._parse_pct(row.get('净利润同比增长率', 0)),
                    revenue=cls._parse_cn_number(row.get('营业总收入', 0)),
                    net_profit=cls._parse_cn_number(row.get('净利润', 0)),
                    eps=float(row.get('基本每股收益', 0) or 0),
                    debt_ratio=cls._parse_pct(row.get('资产负债率', 0)),
                    current_ratio=float(row.get('流动比率', 0) or 0),
                    roa=roa_map.get(yr, 0),
                )))
            return result
        except Exception as e:
            print(f"[Finance] A-share history error {code}: {e}")
            return []


class BaostockAPI:
    """Baostock - 历史和财务数据"""
    
    _logged_in = False
    _lock = threading.Lock()
    
    @classmethod
    def login(cls):
        if not BAOSTOCK_AVAILABLE:
            return False
        with cls._lock:
            if not cls._logged_in:
                result = bs.login()
                cls._logged_in = (result.error_code == '0')
        return cls._logged_in
    
    @classmethod
    def logout(cls):
        with cls._lock:
            if cls._logged_in:
                try:
                    bs.logout()
                except:
                    pass
                cls._logged_in = False
    
    @staticmethod
    def _code(code: str) -> str:
        """Format code for Baostock.
        Index rules: 000xxx→sh (上证指数), 399xxx→sz (深证指数)
        Stock rules: 6xxxxx→sh (沪市), 0/3xxxxx→sz (深市)
        """
        code = str(code).zfill(6)
        # Indices
        if code.startswith('000') and len(code) == 6 and code <= '000999':
            return f"sh.{code}"  # 上证指数 (000001=上证综指, 000300=沪深300)
        if code.startswith('399'):
            return f"sz.{code}"  # 深证指数 (399001=深成指, 399006=创业板指)
        # Stocks
        if code.startswith('6'):
            return f"sh.{code}"
        return f"sz.{code}"
    
    @classmethod
    def get_history(cls, code: str, days: int = 120) -> pd.DataFrame:
        if not cls.login():
            return pd.DataFrame()
        
        bs_code = cls._code(code)
        end = datetime.now().strftime('%Y-%m-%d')
        start = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        
        try:
            rs = bs.query_history_k_data_plus(
                bs_code, "date,open,high,low,close,volume,amount,pctChg",
                start_date=start, end_date=end, frequency="d", adjustflag="2"
            )
            if rs.error_code != '0':
                return pd.DataFrame()
            
            data = []
            while rs.next():
                data.append(rs.get_row_data())
            
            if not data:
                return pd.DataFrame()
            
            df = pd.DataFrame(data, columns=rs.fields)
            for col in ['open', 'high', 'low', 'close', 'volume', 'amount', 'pctChg']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            return df
        except Exception as e:
            print(f"[Baostock] History error {code}: {e}")
            return pd.DataFrame()
    
    @classmethod
    def get_financials(cls, code: str) -> StockFinancials:
        if not cls.login():
            return StockFinancials(code=code)
        
        bs_code = cls._code(code)
        fin = StockFinancials(code=code, timestamp=datetime.now().isoformat())
        year = datetime.now().year - 1
        
        # Try multiple quarters until we find data (Q4 may not be published yet)
        profit_found = False
        for y, q in [(year, 4), (year, 3), (year, 2), (year-1, 4)]:
            if profit_found:
                break
            try:
                rs = bs.query_profit_data(code=bs_code, year=y, quarter=q)
                if rs.error_code == '0' and rs.next():
                    d = dict(zip(rs.fields, rs.get_row_data()))
                    roe = float(d.get('roeAvg', 0) or 0) * 100
                    if roe != 0 or float(d.get('npMargin', 0) or 0) != 0:
                        fin.roe = roe
                        fin.net_margin = float(d.get('npMargin', 0) or 0) * 100
                        fin.gross_margin = float(d.get('gpMargin', 0) or 0) * 100
                        profit_found = True
            except:
                pass
        
        growth_found = False
        for y, q in [(year, 4), (year, 3), (year, 2), (year-1, 4)]:
            if growth_found:
                break
            try:
                rs = bs.query_growth_data(code=bs_code, year=y, quarter=q)
                if rs.error_code == '0' and rs.next():
                    d = dict(zip(rs.fields, rs.get_row_data()))
                    rev = float(d.get('YOYEquity', 0) or 0) * 100
                    profit = float(d.get('YOYNI', 0) or 0) * 100
                    if rev != 0 or profit != 0:
                        fin.revenue_growth = rev
                        fin.profit_growth = profit
                        growth_found = True
            except:
                pass
        
        # ROA only for banks (debt_ratio > 80% = likely bank/insurance)
        # Banks have no gross margin, ROA is their core profitability metric
        if fin.gross_margin == 0 and fin.roe > 0:
            try:
                for y, q in [(year, 4), (year, 3), (year-1, 4)]:
                    rs = bs.query_dupont_data(code=bs_code, year=y, quarter=q)
                    if rs.error_code == '0' and rs.next():
                        d = dict(zip(rs.fields, rs.get_row_data()))
                        roe_d = float(d.get('dupontROE', 0) or 0)
                        leverage = float(d.get('dupontAssetStoEquity', 0) or 0)
                        if roe_d > 0 and leverage > 0:
                            fin.roa = roe_d / leverage * 100
                            break
            except:
                pass
        
        return fin


class StockDataProvider:
    """统一数据提供者"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance
    
    def _init(self):
        self.cache = SimpleCache()
        self.api_calls = 0
    
    def reset_stats(self):
        self.api_calls = 0
    
    def get_quotes(self, codes: List[str]) -> Dict[str, StockQuote]:
        """获取实时行情 (1分钟缓存), A股用腾讯(有PE/PB), 港股用新浪"""
        key = f"quotes_{'_'.join(sorted(codes))}"
        cached = self.cache.get(key, ttl_min=1)
        if cached:
            return {k: StockQuote(**v) for k, v in cached.items()}
        
        a_codes = [c for c in codes if not str(c).startswith('hk')]
        hk_codes = [c for c in codes if str(c).startswith('hk')]
        
        quotes = {}
        
        # A-shares: Tencent (has PE/PB), Sina fallback
        if a_codes:
            self.api_calls += 1
            quotes.update(TencentAPI.get_quotes(a_codes))
            # Fill missing with Sina
            missing = [c for c in a_codes if c not in quotes]
            if missing:
                self.api_calls += 1
                quotes.update(SinaAPI.get_quotes(missing))
        
        # HK stocks: Sina only
        if hk_codes:
            self.api_calls += 1
            quotes.update(SinaAPI.get_quotes(hk_codes))
        
        if quotes:
            self.cache.set(key, {k: asdict(v) for k, v in quotes.items()})
        return quotes
    
    def get_history(self, code: str, days: int = 120) -> pd.DataFrame:
        """获取历史K线 (4小时缓存), A股用Baostock, 港股用AKShare新浪源"""
        key = f"hist_{code}_{days}"
        cached = self.cache.get(key, ttl_min=240)
        if cached is not None:
            return pd.DataFrame(cached)
        
        self.api_calls += 1
        if str(code).startswith('hk'):
            df = HKStockAPI.get_history(code, days)
        else:
            df = BaostockAPI.get_history(code, days)
        
        if not df.empty:
            self.cache.set(key, df.to_dict('records'))
        return df
    
    def get_financials(self, code: str) -> StockFinancials:
        """获取最新财务数据 (24小时缓存), A股用Baostock, 港股用东方财富"""
        key = f"fin_{code}"
        cached = self.cache.get(key, ttl_min=1440)
        if cached:
            return StockFinancials(**cached)
        
        self.api_calls += 1
        if str(code).startswith('hk'):
            # 港股: 从5年财务中取最新一期
            history = FinancialHistoryAPI.get_hk_history(code, years=1)
            if history:
                h = history[0]
                fin = StockFinancials(
                    code=code,
                    roe=h['roe'], gross_margin=h['gross_margin'],
                    net_margin=h['net_margin'], revenue_growth=h['revenue_growth'],
                    profit_growth=h['profit_growth'], debt_ratio=h['debt_ratio'],
                    current_ratio=h['current_ratio'],
                    timestamp=datetime.now().isoformat()
                )
            else:
                fin = StockFinancials(code=code)
        else:
            fin = BaostockAPI.get_financials(code)
        
        self.cache.set(key, asdict(fin))
        return fin
    
    def get_financial_history(self, code: str, years: int = None) -> List[Dict]:
        """获取多年财务历史 (24小时缓存). A股默认10年, 港股默认5年"""
        if years is None:
            years = 9 if str(code).startswith('hk') else 10
        
        key = f"fin_hist_{code}_{years}"
        cached = self.cache.get(key, ttl_min=1440)
        if cached is not None:
            return cached
        
        self.api_calls += 1
        if str(code).startswith('hk'):
            result = FinancialHistoryAPI.get_hk_history(code, years)
        else:
            result = FinancialHistoryAPI.get_a_share_history(code, years)
        
        if result:
            self.cache.set(key, result)
        return result
    
    def prefetch(self, codes: List[str]):
        """预加载数据"""
        print(f"[Data] Prefetching {len(codes)} stocks...")
        t0 = time.time()
        c0 = self.api_calls
        
        self.get_quotes(codes)
        for code in codes:
            self.get_history(code)
            self.get_financials(code)
        
        print(f"[Data] Done: {self.api_calls - c0} calls, {time.time()-t0:.2f}s")
    
    def cleanup(self):
        BaostockAPI.logout()


def get_provider() -> StockDataProvider:
    return StockDataProvider()
