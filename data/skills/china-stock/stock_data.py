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
    """财务数据"""
    code: str
    roe: float = 0.0
    gross_margin: float = 0.0
    net_margin: float = 0.0
    revenue_growth: float = 0.0
    profit_growth: float = 0.0
    debt_ratio: float = 0.0
    current_ratio: float = 0.0
    timestamp: str = ""


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
    """新浪财经实时行情 - 最快，但没有PE/PB"""
    
    @staticmethod
    def get_quotes(codes: List[str]) -> Dict[str, StockQuote]:
        if not codes:
            return {}
        
        sina_codes = []
        for c in codes:
            c = str(c).zfill(6)
            sina_codes.append(f"sh{c}" if c.startswith('6') else f"sz{c}")
        
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
            
            code = match.group(1)[2:]
            parts = match.group(2).split(',')
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
    """腾讯财经 API - 提供 PE/PB 数据"""
    
    @staticmethod
    def get_quotes(codes: List[str]) -> Dict[str, StockQuote]:
        if not codes:
            return {}
        
        qq_codes = []
        for c in codes:
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
        """获取实时行情 (1分钟缓存), 使用腾讯API(有PE/PB)，新浪备用"""
        key = f"quotes_{'_'.join(sorted(codes))}"
        cached = self.cache.get(key, ttl_min=1)
        if cached:
            return {k: StockQuote(**v) for k, v in cached.items()}
        
        # Primary: Tencent (has PE/PB)
        self.api_calls += 1
        quotes = TencentAPI.get_quotes(codes)
        
        # Fallback: Sina (faster but no PE/PB)
        if not quotes:
            self.api_calls += 1
            quotes = SinaAPI.get_quotes(codes)
        
        if quotes:
            self.cache.set(key, {k: asdict(v) for k, v in quotes.items()})
        return quotes
    
    def get_history(self, code: str, days: int = 120) -> pd.DataFrame:
        """获取历史K线 (4小时缓存)"""
        key = f"hist_{code}_{days}"
        cached = self.cache.get(key, ttl_min=240)
        if cached is not None:
            return pd.DataFrame(cached)
        
        self.api_calls += 1
        df = BaostockAPI.get_history(code, days)
        if not df.empty:
            self.cache.set(key, df.to_dict('records'))
        return df
    
    def get_financials(self, code: str) -> StockFinancials:
        """获取财务数据 (24小时缓存)"""
        key = f"fin_{code}"
        cached = self.cache.get(key, ttl_min=1440)
        if cached:
            return StockFinancials(**cached)
        
        self.api_calls += 1
        fin = BaostockAPI.get_financials(code)
        self.cache.set(key, asdict(fin))
        return fin
    
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
