#!/usr/bin/env python3
"""
Stock Analyzers - Industry-Aware Scoring

行业感知的评分系统：
- 不同行业使用不同的评分标准（银行看PB/NIM，白酒看PE/毛利）
- 周期股在底部不会被错判为"垃圾"
- 金融股毛利率=0不会被扣分
"""

import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, Optional
from dataclasses import dataclass, asdict
from stock_data import StockQuote, StockFinancials


# 行业评分参数 - 不同行业用不同标准
INDUSTRY_PROFILES = {
    'default': {
        'roe_excellent': 20, 'roe_good': 15, 'roe_ok': 10,
        'gm_weight': 10, 'nm_weight': 10,
        'pe_low': 15, 'pe_fair': 25, 'pe_high': 40,
        'use_pb': False,
    },
    'bank': {  # J66 银行 - 看PB不看PE，无毛利率概念
        'roe_excellent': 15, 'roe_good': 11, 'roe_ok': 8,
        'gm_weight': 0, 'nm_weight': 10,  # 银行无毛利率
        'pe_low': 5, 'pe_fair': 8, 'pe_high': 12,
        'use_pb': True, 'pb_low': 0.5, 'pb_fair': 0.8, 'pb_high': 1.2,
    },
    'insurance': {  # J68 保险 - 看PEV不看PE
        'roe_excellent': 18, 'roe_good': 13, 'roe_ok': 9,
        'gm_weight': 0, 'nm_weight': 10,
        'pe_low': 8, 'pe_fair': 12, 'pe_high': 18,
        'use_pb': True, 'pb_low': 0.6, 'pb_fair': 1.0, 'pb_high': 1.5,
    },
    'broker': {  # J67 资本市场 - 强周期
        'roe_excellent': 15, 'roe_good': 10, 'roe_ok': 6,
        'gm_weight': 8, 'nm_weight': 10,
        'pe_low': 15, 'pe_fair': 25, 'pe_high': 40,
        'use_pb': False,
    },
    'baijiu': {  # C15 白酒 - 高毛利高ROE
        'roe_excellent': 30, 'roe_good': 20, 'roe_ok': 15,
        'gm_weight': 10, 'nm_weight': 10,
        'pe_low': 20, 'pe_fair': 30, 'pe_high': 45,
        'use_pb': False,
    },
    'cyclical': {  # 周期股 - ROE波动大是正常的
        'roe_excellent': 15, 'roe_good': 8, 'roe_ok': 3,
        'gm_weight': 8, 'nm_weight': 8,
        'pe_low': 10, 'pe_fair': 20, 'pe_high': 35,
        'use_pb': False,
    },
}

def get_industry_profile(stock_meta: Dict = None) -> Dict:
    """根据股票元数据选择行业评分参数"""
    if not stock_meta:
        return INDUSTRY_PROFILES['default']

    sub = (stock_meta.get('sub_industry', '') + stock_meta.get('_industry', '')).lower()

    if 'j66' in sub or '银行' in sub:
        return INDUSTRY_PROFILES['bank']
    elif 'j68' in sub or '保险' in sub:
        return INDUSTRY_PROFILES['insurance']
    elif 'j67' in sub or '券商' in sub:
        return INDUSTRY_PROFILES['broker']
    elif 'c15' in sub or '白酒' in sub:
        return INDUSTRY_PROFILES['baijiu']
    elif stock_meta.get('lynch_category') == 'cyclical':
        return INDUSTRY_PROFILES['cyclical']
    else:
        return INDUSTRY_PROFILES['default']


@dataclass
class AnalysisResult:
    code: str
    name: str
    price: float
    score: float
    max_score: float
    rating: str
    emoji: str
    details: Dict


class TechCalc:
    """技术指标计算"""
    
    @staticmethod
    def ma(s: pd.Series, n: int) -> pd.Series:
        return s.rolling(n).mean()
    
    @staticmethod
    def rsi(s: pd.Series, n: int = 14) -> float:
        d = s.diff()
        g = d.where(d > 0, 0).rolling(n).mean()
        l = (-d.where(d < 0, 0)).rolling(n).mean()
        rs = g / l.replace(0, np.inf)
        rsi = 100 - (100 / (1 + rs))
        return float(rsi.iloc[-1]) if len(rsi) > 0 else 50
    
    @staticmethod
    def strength(s: pd.Series, days: int = 60) -> float:
        if len(s) < days:
            return 50
        chg = (s.iloc[-1] / s.iloc[-days] - 1) * 100
        return max(0, min(100, 50 + chg / 3))


class CANSLIMAnalyzer:
    """CANSLIM 分析 (William O'Neil)"""
    
    def analyze(self, q: StockQuote, f: StockFinancials, df: pd.DataFrame) -> AnalysisResult:
        scores = {}
        details = {}
        
        # C - 当季盈利
        g = f.profit_growth
        scores['C'] = 15 if g >= 25 else 12 if g >= 15 else 8 if g >= 0 else 3
        details['C'] = f"盈利增长: {g:.1f}%"
        
        # A - 年度增长
        g = f.revenue_growth
        scores['A'] = 15 if g >= 25 else 12 if g >= 15 else 8 if g >= 5 else 3
        details['A'] = f"营收增长: {g:.1f}%"
        
        # N - 创新高
        if not df.empty and 'close' in df.columns:
            p = df['close'].dropna()
            if len(p) >= 20:
                pct = (p.iloc[-1] / p.max()) * 100
                scores['N'] = 15 if pct >= 95 else 12 if pct >= 85 else 8 if pct >= 70 else 3
                details['N'] = f"距高点: {pct:.1f}%"
            else:
                scores['N'] = 7
                details['N'] = "数据不足"
        else:
            scores['N'] = 7
            details['N'] = "无数据"
        
        # S - 供需
        if not df.empty and 'volume' in df.columns:
            v = df['volume'].dropna()
            if len(v) >= 20:
                ratio = v.iloc[-5:].mean() / v.rolling(20).mean().iloc[-1]
                scores['S'] = 15 if ratio >= 1.5 else 12 if ratio >= 1.2 else 8 if ratio >= 0.8 else 5
                details['S'] = f"量比: {ratio:.2f}"
            else:
                scores['S'] = 7
                details['S'] = "数据不足"
        else:
            scores['S'] = 7
            details['S'] = "无数据"
        
        # L - 领导股
        if not df.empty and 'close' in df.columns:
            rs = TechCalc.strength(df['close'].dropna())
            scores['L'] = 15 if rs >= 80 else 12 if rs >= 60 else 8 if rs >= 40 else 3
            details['L'] = f"相对强度: {rs:.0f}"
        else:
            scores['L'] = 7
            details['L'] = "无数据"
        
        # I - 机构 (用ROE代替)
        roe = f.roe
        scores['I'] = 15 if roe >= 20 else 12 if roe >= 15 else 8 if roe >= 10 else 5
        details['I'] = f"ROE: {roe:.1f}%"
        
        # M - 大盘
        if not df.empty and 'close' in df.columns:
            p = df['close'].dropna()
            if len(p) >= 50:
                ma20 = TechCalc.ma(p, 20).iloc[-1]
                ma50 = TechCalc.ma(p, 50).iloc[-1]
                cur = p.iloc[-1]
                if cur > ma20 > ma50:
                    scores['M'] = 10
                    details['M'] = "上升趋势"
                elif cur > ma20:
                    scores['M'] = 7
                    details['M'] = "MA20上方"
                else:
                    scores['M'] = 4
                    details['M'] = "MA20下方"
            else:
                scores['M'] = 5
                details['M'] = "数据不足"
        else:
            scores['M'] = 5
            details['M'] = "无数据"
        
        total = sum(scores.values())
        norm = total / 100 * 100
        
        if norm >= 80:
            rating, emoji = "强烈买入", "🚀"
        elif norm >= 65:
            rating, emoji = "买入", "🟢"
        elif norm >= 50:
            rating, emoji = "持有", "🟡"
        else:
            rating, emoji = "回避", "🔴"
        
        return AnalysisResult(q.code, q.name, q.price, total, 100, rating, emoji,
                             {'scores': scores, 'details': details, 'method': 'CANSLIM'})


class ValueAnalyzer:
    """价值投资分析 (段永平/巴菲特) - 行业感知版"""
    
    def analyze(self, q: StockQuote, f: StockFinancials, df: pd.DataFrame, stock_meta: Dict = None) -> AnalysisResult:
        scores = {}
        details = {}
        flags = []
        
        ip = get_industry_profile(stock_meta)
        
        # ROE (0-25) - 使用行业标准
        roe = f.roe
        if roe >= ip['roe_excellent']:
            scores['roe'] = 25
        elif roe >= ip['roe_good']:
            scores['roe'] = 20
        elif roe >= ip['roe_ok']:
            scores['roe'] = 15
        elif roe > 0:
            scores['roe'] = 8
            # 周期股在底部ROE低是正常的
            if stock_meta and stock_meta.get('lynch_category') == 'cyclical':
                flags.append("周期底部ROE偏低")
            else:
                flags.append("低ROE")
        else:
            scores['roe'] = 3
            if stock_meta and stock_meta.get('lynch_category') in ('cyclical', 'turnaround'):
                flags.append("周期/反转中ROE为负")
            else:
                flags.append("ROE为负")
        details['roe'] = f"ROE: {roe:.1f}%"
        
        # 利润率 (0-20) - 银行用ROA替代毛利率
        gm, nm = f.gross_margin, f.net_margin
        gm_score = 0
        if ip['gm_weight'] > 0:
            gm_score = ip['gm_weight'] if gm >= 40 else int(ip['gm_weight']*0.6) if gm >= 25 else int(ip['gm_weight']*0.2)
        else:
            # 银行/保险: 用ROA替代毛利率评分 (银行ROA 1%+为优秀)
            roa = f.roa
            if roa >= 1.2:
                gm_score = 10
            elif roa >= 0.8:
                gm_score = 7
            elif roa >= 0.5:
                gm_score = 4
            elif roa > 0:
                gm_score = 2
        nm_score = ip['nm_weight'] if nm >= 15 else int(ip['nm_weight']*0.6) if nm >= 8 else int(ip['nm_weight']*0.2)
        scores['margin'] = gm_score + nm_score
        if ip['gm_weight'] > 0:
            details['margin'] = f"毛利{gm:.1f}% 净利{nm:.1f}%"
        else:
            roa = f.roa
            details['margin'] = f"ROA:{roa:.2f}% 净利率:{nm:.1f}% (银行用ROA替代毛利)"
        
        # 财务健康 (0-20)
        scores['health'] = 15
        details['health'] = "财务稳健"
        
        # 估值 (0-20) - 行业定制
        pe = q.pe if q.pe > 0 else ip['pe_fair']
        pb = q.pb if q.pb > 0 else 1
        
        if ip.get('use_pb'):
            # 银行/保险用PB估值
            pb_low = ip.get('pb_low', 0.5)
            pb_fair = ip.get('pb_fair', 0.8)
            pb_high = ip.get('pb_high', 1.2)
            pb_s = 12 if pb <= pb_low else 9 if pb <= pb_fair else 5 if pb <= pb_high else 1
            pe_s = 8 if pe <= ip['pe_low'] else 5 if pe <= ip['pe_fair'] else 2 if pe <= ip['pe_high'] else 0
            scores['val'] = pb_s + pe_s
            details['val'] = f"PB:{pb:.2f} PE:{pe:.1f}"
            if pb > pb_high:
                flags.append(f"PB {pb:.1f}偏高")
        else:
            pe_s = 10 if pe <= ip['pe_low'] else 7 if pe <= ip['pe_fair'] else 4 if pe <= ip['pe_high'] else 1
            pb_s = 10 if pb <= 2 else 7 if pb <= 4 else 4 if pb <= 6 else 1
            scores['val'] = pe_s + pb_s
            details['val'] = f"PE:{pe:.1f} PB:{pb:.1f}"
            if pe > ip['pe_high']:
                flags.append("高PE")
        
        # 成长 (0-15) - 周期股负增长不一定是坏事（可能是底部）
        g = f.profit_growth
        if 20 <= g <= 50:
            scores['growth'] = 15
        elif g >= 10:
            scores['growth'] = 12
        elif g >= 0:
            scores['growth'] = 8
        else:
            if stock_meta and stock_meta.get('lynch_category') in ('cyclical', 'turnaround'):
                scores['growth'] = 5  # 周期/反转股轻罚
            else:
                scores['growth'] = 3
                flags.append("负增长")
        details['growth'] = f"利润增长: {g:.1f}%"
        
        total = sum(scores.values())
        
        if total >= 75 and not flags:
            rating, emoji = "优质价值", "💎"
        elif total >= 60 and len(flags) <= 1:
            rating, emoji = "良好价值", "🟢"
        elif total >= 45:
            rating, emoji = "一般", "🟡"
        else:
            rating, emoji = "回避", "🔴"
        
        return AnalysisResult(q.code, q.name, q.price, total, 100, rating, emoji,
                             {'scores': scores, 'details': details, 'flags': flags, 'method': 'Value'})


class GrowthAnalyzer:
    """成长股分析 (彼得林奇) - 行业感知版"""
    
    def analyze(self, q: StockQuote, f: StockFinancials, df: pd.DataFrame, stock_meta: Dict = None) -> AnalysisResult:
        scores = {}
        details = {}
        
        lynch_cat = stock_meta.get('lynch_category', '') if stock_meta else ''
        
        # PEG (0-30) - 周期股/反转股不适用PEG
        pe = q.pe if q.pe > 0 else 20
        g = max(f.profit_growth, 1)
        
        if lynch_cat in ('cyclical', 'turnaround') and f.profit_growth <= 0:
            # 周期底部/反转中，PEG无意义，用PB或PE绝对值
            if pe <= 15:
                scores['peg'] = 20
            elif pe <= 25:
                scores['peg'] = 15
            else:
                scores['peg'] = 8
            peg = 0
            details['peg'] = f"PE:{pe:.1f} (周期股不适用PEG)"
        else:
            peg = pe / g if g > 0 else 99
            if peg <= 0.5:
                scores['peg'] = 30
            elif peg <= 1.0:
                scores['peg'] = 25
            elif peg <= 1.5:
                scores['peg'] = 18
            elif peg <= 2.0:
                scores['peg'] = 12
            else:
                scores['peg'] = 5
            details['peg'] = f"PEG:{peg:.2f} (PE:{pe:.1f}/G:{g:.1f}%)"
        
        # 增长率 (0-25)
        if g >= 25:
            scores['growth'] = 25
            cat = "快速成长"
        elif g >= 15:
            scores['growth'] = 20
            cat = "稳健成长"
        elif g >= 5:
            scores['growth'] = 12
            cat = "缓慢成长"
        else:
            scores['growth'] = 5
            cat = "衰退"
        details['growth'] = f"{g:.1f}% ({cat})"
        
        # 质量 (0-25)
        roe, nm = f.roe, f.net_margin
        qs = (12 if roe >= 15 else 8 if roe >= 10 else 4) + (13 if nm >= 10 else 8 if nm >= 5 else 4)
        scores['quality'] = qs
        details['quality'] = f"ROE:{roe:.1f}% 净利率:{nm:.1f}%"
        
        # 趋势 (0-20)
        if not df.empty and 'close' in df.columns:
            p = df['close'].dropna()
            if len(p) >= 20:
                ma20 = TechCalc.ma(p, 20).iloc[-1]
                pct = ((p.iloc[-1] / ma20) - 1) * 100 if ma20 > 0 else 0
                scores['trend'] = 20 if pct >= 5 else 15 if pct >= 0 else 10 if pct >= -10 else 5
                details['trend'] = f"MA20: {pct:+.1f}%"
            else:
                scores['trend'] = 10
                details['trend'] = "数据不足"
        else:
            scores['trend'] = 10
            details['trend'] = "无数据"
        
        total = sum(scores.values())
        
        if total >= 75:
            rating, emoji = "强成长", "🚀"
        elif total >= 60:
            rating, emoji = "好成长", "🟢"
        elif total >= 45:
            rating, emoji = "一般", "🟡"
        else:
            rating, emoji = "弱势", "🔴"
        
        return AnalysisResult(q.code, q.name, q.price, total, 100, rating, emoji,
                             {'scores': scores, 'details': details, 'category': cat, 'peg': peg, 'method': 'Growth'})


class MasterAnalyzer:
    """综合分析 - 三种方法加权(行业感知)"""
    
    def __init__(self):
        self.canslim = CANSLIMAnalyzer()
        self.value = ValueAnalyzer()
        self.growth = GrowthAnalyzer()
        self.weights = {'canslim': 0.30, 'value': 0.35, 'growth': 0.35}
    
    def analyze(self, q: StockQuote, f: StockFinancials, df: pd.DataFrame, stock_meta: Dict = None) -> Dict:
        c = self.canslim.analyze(q, f, df)
        v = self.value.analyze(q, f, df, stock_meta)
        g = self.growth.analyze(q, f, df, stock_meta)
        
        cn = c.score / c.max_score * 100
        vn = v.score / v.max_score * 100
        gn = g.score / g.max_score * 100
        
        master = cn * 0.30 + vn * 0.35 + gn * 0.35
        
        ratings = [c.rating, v.rating, g.rating]
        buys = sum(1 for r in ratings if '买' in r or '价值' in r or '成长' in r)
        
        if buys == 3:
            mr, me = "强烈推荐", "💎🚀"
        elif buys >= 2 and master >= 65:
            mr, me = "高度看好", "🟢🟢"
        elif buys >= 2:
            mr, me = "买入", "🟢"
        elif master >= 55:
            mr, me = "持有", "🟡"
        else:
            mr, me = "回避", "🔴"
        
        return {
            'code': q.code,
            'name': q.name,
            'price': q.price,
            'master_score': master,
            'master_rating': mr,
            'master_emoji': me,
            'canslim': asdict(c),
            'value': asdict(v),
            'growth': asdict(g),
            'consensus': {'buys': buys, 'total': 3},
            'timestamp': datetime.now().isoformat()
        }


# ============================================================
# Screener helper functions (used by screener.py)
# ============================================================

def to_weekly(df: pd.DataFrame) -> pd.DataFrame:
    """Resample daily K-lines to weekly (W-FRI) bars.

    Input columns expected: date, open, high, low, close, volume[, amount]
    Returns weekly DataFrame indexed by week-end Friday with the same columns.
    """
    if df is None or df.empty or 'date' not in df.columns:
        return pd.DataFrame()

    try:
        d = df.copy()
        d['date'] = pd.to_datetime(d['date'])
        d = d.set_index('date').sort_index()

        agg = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}
        if 'amount' in d.columns:
            agg['amount'] = 'sum'

        w = d.resample('W-FRI').agg(agg).dropna(subset=['close'])
        return w
    except Exception:
        return pd.DataFrame()


def detect_weekly_volume_accumulation(weekly_df: pd.DataFrame,
                                      lookback_weeks: int = 8,
                                      vol_ratio_min: float = 1.10,
                                      consecutive_weeks: int = 3,
                                      max_pct_from_low: float = 35.0,
                                      min_pct_from_high: float = 25.0,
                                      max_volatility_pct: float = 12.0,
                                      uptrend_weeks: int = 3,
                                      uptrend_min_pct: float = 3.0) -> tuple:
    """Detect weekly bottom volume accumulation pattern.

    Conditions:
      1. Stock is near 52w low (<=max_pct_from_low above 52w low)
      2. Stock is far from 52w high (>=min_pct_from_high below 52w high)
      3. Weekly volume has been >= MA20 * vol_ratio_min for >= consecutive_weeks recent weeks
      4. Weekly volatility is moderate (avg weekly range pct <= max_volatility_pct)
      5. Total accumulation period >= lookback_weeks weeks of data
      6. **Recent uptrend confirmation**: latest close >= close N weeks ago * (1 + min_pct/100)
         (Avoid stocks that are accumulating volume but still flat/falling — we want
         price to have already started turning up.)

    Returns: (matched: bool, evidence: dict). Evidence always includes peak_vol_ratio
    so the caller can apply additional logic (e.g. extreme-volume override).
    """
    evidence = {}

    if weekly_df is None or weekly_df.empty:
        return False, {'reason': 'no_weekly_data'}
    if len(weekly_df) < max(lookback_weeks, 20):
        return False, {'reason': f'insufficient_weeks_{len(weekly_df)}'}

    try:
        c = weekly_df['close'].astype(float)
        v = weekly_df['volume'].astype(float)
        h = weekly_df['high'].astype(float)
        l = weekly_df['low'].astype(float)

        cur = float(c.iloc[-1])
        # 52-week range (use last 52 weeks if available)
        recent = c.tail(52)
        hi_52w = float(recent.max())
        lo_52w = float(recent.min())
        pct_from_low = (cur / lo_52w - 1) * 100 if lo_52w > 0 else 999
        pct_from_high = (1 - cur / hi_52w) * 100 if hi_52w > 0 else 0

        evidence['cur_close'] = round(cur, 2)
        evidence['hi_52w'] = round(hi_52w, 2)
        evidence['lo_52w'] = round(lo_52w, 2)
        evidence['pct_from_low'] = round(pct_from_low, 2)
        evidence['pct_from_high'] = round(pct_from_high, 2)

        # Volume MA20 on weekly bars (compute first so we can always emit ratios)
        vol_ma = v.rolling(20).mean()
        cur_ma = float(vol_ma.iloc[-1]) if not vol_ma.empty else 0
        if cur_ma <= 0 or pd.isna(cur_ma):
            return False, {**evidence, 'reason': 'no_vol_baseline'}

        ratios = (v / vol_ma).fillna(0)
        recent_ratios = ratios.tail(lookback_weeks)
        # Count longest tail of consecutive weeks meeting threshold
        consec = 0
        for r in reversed(recent_ratios.tolist()):
            if r >= vol_ratio_min:
                consec += 1
            else:
                break
        # Peak ratio across the consec window (or recent lookback if no streak)
        peak_window = consec if consec > 0 else lookback_weeks
        peak_ratio = float(ratios.tail(peak_window).max()) if peak_window > 0 else 0.0
        evidence['consec_high_vol_weeks'] = consec
        evidence['avg_vol_ratio'] = round(float(recent_ratios.mean()), 2)
        evidence['last_vol_ratio'] = round(float(ratios.iloc[-1]), 2)
        evidence['peak_vol_ratio'] = round(peak_ratio, 2)

        # Recent uptrend: close N weeks ago vs current
        if uptrend_weeks > 0 and len(c) > uptrend_weeks:
            base = float(c.iloc[-(uptrend_weeks + 1)])
            uptrend_pct = (cur / base - 1) * 100 if base > 0 else 0
        else:
            uptrend_pct = 0
        evidence['recent_uptrend_pct'] = round(uptrend_pct, 2)
        evidence['uptrend_window_weeks'] = uptrend_weeks

        # Position checks (must be at bottom area)
        if pct_from_low > max_pct_from_low:
            return False, {**evidence, 'reason': f'far_from_low_{pct_from_low:.1f}%'}
        if pct_from_high < min_pct_from_high:
            return False, {**evidence, 'reason': f'too_close_to_high_{pct_from_high:.1f}%'}

        if consec < consecutive_weeks:
            return False, {**evidence, 'reason': f'consecutive_weeks_{consec}<{consecutive_weeks}'}

        # Volatility check (average weekly range %)
        rng_pct = ((h - l) / c.replace(0, 1)) * 100
        avg_vol_pct = float(rng_pct.tail(lookback_weeks).mean())
        evidence['avg_weekly_range_pct'] = round(avg_vol_pct, 2)
        if avg_vol_pct > max_volatility_pct:
            return False, {**evidence, 'reason': f'too_volatile_{avg_vol_pct:.1f}%'}

        # Recent uptrend gate (走势向上确认)
        if uptrend_weeks > 0 and uptrend_pct < uptrend_min_pct:
            return False, {
                **evidence,
                'reason': f'no_recent_uptrend_{uptrend_pct:.1f}%<{uptrend_min_pct}% (近{uptrend_weeks}周)',
            }

        # Total accumulation duration: weeks where price stayed within 25% of current low
        floor = lo_52w * 1.25
        accum_weeks = int((c.tail(lookback_weeks * 2) <= floor * 1.5).sum())
        evidence['accumulation_weeks_estimate'] = accum_weeks

        return True, evidence

    except Exception as e:
        return False, {'reason': f'error: {e}'}


def detect_new_high_breakout(daily_df: pd.DataFrame,
                             weekly_df: pd.DataFrame = None,
                             max_pct_from_high: float = 10.0,
                             min_relative_strength: float = 60.0,
                             vol_breakout_ratio_min: float = 0.9,
                             weekly_vol_ratio_min: float = 1.0,
                             ma_alignment_required: bool = True,
                             max_distance_from_ma20_pct: float = 25.0,
                             min_pct_above_ma60: float = 10.0,
                             max_pct_above_ma60: float = 60.0,
                             min_weeks_above_ma20: int = 4) -> tuple:
    """Detect new-high breakout pattern with strong momentum.

    Defaults tuned from the empirical study of 42 YTD ≥50% gainers (2026 H1):
      - 距 MA60 是最强的"分级"指标 (底部 -2.5% → 翻倍 +38.9%)
      - 5/20 日量比无区分力 (各梯队都在 1.0-1.2)
      - 距 52w 高 ≤10% 覆盖 84% 牛股 (5% 仅覆盖 55%)
      - RS ≥60 覆盖 78% 牛股 (80 仅覆盖 25%)

    Conditions (all must hold):
      1. Price within max_pct_from_high% of 52-week high
      2. Relative strength (60-day return) >= min_relative_strength
      3. Volume confirmation — at least ONE of:
           a) 5-day avg volume / 20-day avg volume >= vol_breakout_ratio_min
           b) recent weekly volume / weekly MA20 >= weekly_vol_ratio_min
      4. MA alignment: price > MA5 > MA10 > MA20 (if required)
      5. Price within max_distance_from_ma20_pct% above MA20 (avoid extreme chase)
      6. **Distance above MA60**: between min_pct_above_ma60 and max_pct_above_ma60.
         This is the strongest grading indicator: 50-100% group median +21%,
         ≥100% group median +39%. Below 10% means trend not yet established;
         above 60% means already overheated.
      7. On weekly: closed above MA20-weekly for >= min_weeks_above_ma20 weeks

    All metrics are populated in `evidence` regardless of which check failed,
    so callers can build diagnostic dashboards.

    Returns: (matched: bool, evidence: dict)
    """
    evidence = {}

    if daily_df is None or daily_df.empty or 'close' not in daily_df.columns:
        return False, {'reason': 'no_daily_data'}
    if len(daily_df) < 60:
        return False, {'reason': f'insufficient_days_{len(daily_df)}'}

    try:
        c = daily_df['close'].astype(float)
        v = daily_df['volume'].astype(float) if 'volume' in daily_df.columns else pd.Series()

        cur = float(c.iloc[-1])
        hi_52w = float(c.tail(252).max() if len(c) >= 252 else c.max())
        pct_from_high = (1 - cur / hi_52w) * 100 if hi_52w > 0 else 100

        # Compute ALL metrics first so evidence is complete for diagnostics
        evidence['cur_close'] = round(cur, 2)
        evidence['hi_52w'] = round(hi_52w, 2)
        evidence['pct_from_high'] = round(pct_from_high, 2)

        rs = TechCalc.strength(c, days=60)
        evidence['relative_strength'] = round(rs, 2)

        vol_ratio_daily = None
        if len(v) >= 20:
            v5 = float(v.tail(5).mean())
            v20 = float(v.tail(20).mean())
            vol_ratio_daily = v5 / v20 if v20 > 0 else 0
            evidence['vol_5d_vs_20d'] = round(vol_ratio_daily, 2)

        vol_ratio_weekly = None
        weeks_above = None
        if weekly_df is not None and not weekly_df.empty and len(weekly_df) >= 20:
            wv = weekly_df['volume'].astype(float)
            w_ma20_v = wv.rolling(20).mean()
            cur_w_ma = float(w_ma20_v.iloc[-1]) if not w_ma20_v.empty else 0
            if cur_w_ma > 0:
                # Recent 4-week average volume vs weekly MA20
                recent_w_avg = float(wv.tail(4).mean())
                vol_ratio_weekly = recent_w_avg / cur_w_ma
                evidence['vol_weekly_4w_vs_ma20'] = round(vol_ratio_weekly, 2)

            wc = weekly_df['close'].astype(float)
            w_ma20_c = wc.rolling(20).mean()
            recent = (wc.tail(min_weeks_above_ma20 + 2) >
                      w_ma20_c.tail(min_weeks_above_ma20 + 2)).fillna(False)
            consec = 0
            for above in reversed(recent.tolist()):
                if above:
                    consec += 1
                else:
                    break
            weeks_above = consec
            evidence['weeks_above_w_ma20'] = consec

        ma5 = float(TechCalc.ma(c, 5).iloc[-1])
        ma10 = float(TechCalc.ma(c, 10).iloc[-1])
        ma20 = float(TechCalc.ma(c, 20).iloc[-1])
        ma60 = float(TechCalc.ma(c, 60).iloc[-1]) if len(c) >= 60 else ma20
        evidence['ma5'] = round(ma5, 2)
        evidence['ma10'] = round(ma10, 2)
        evidence['ma20'] = round(ma20, 2)
        evidence['ma60'] = round(ma60, 2)

        dist_ma20 = (cur / ma20 - 1) * 100 if ma20 > 0 else 0
        dist_ma60 = (cur / ma60 - 1) * 100 if ma60 > 0 else 0
        evidence['pct_above_ma20'] = round(dist_ma20, 2)
        evidence['pct_above_ma60'] = round(dist_ma60, 2)

        # Now apply gates (all metrics already in evidence)
        if pct_from_high > max_pct_from_high:
            return False, {**evidence, 'reason': f'not_near_high_{pct_from_high:.1f}%'}

        if rs < min_relative_strength:
            return False, {**evidence, 'reason': f'rs_{rs:.1f}<{min_relative_strength}'}

        # Dual volume gate: pass if either daily 5/20 OR weekly 4w/MA20 confirms
        vol_ok_daily = (vol_ratio_daily is not None and vol_ratio_daily >= vol_breakout_ratio_min)
        vol_ok_weekly = (vol_ratio_weekly is not None and vol_ratio_weekly >= weekly_vol_ratio_min)
        if not (vol_ok_daily or vol_ok_weekly):
            d_str = f"{vol_ratio_daily:.2f}" if vol_ratio_daily is not None else 'na'
            w_str = f"{vol_ratio_weekly:.2f}" if vol_ratio_weekly is not None else 'na'
            return False, {
                **evidence,
                'reason': f'vol_weak: 5/20={d_str}<{vol_breakout_ratio_min} and 4w/MA20={w_str}<{weekly_vol_ratio_min}'
            }
        evidence['vol_ok_daily'] = bool(vol_ok_daily)
        evidence['vol_ok_weekly'] = bool(vol_ok_weekly)

        if ma_alignment_required and not (cur > ma5 and ma5 > ma10 and ma10 > ma20):
            return False, {**evidence, 'reason': 'ma_not_aligned'}

        if dist_ma20 > max_distance_from_ma20_pct:
            return False, {**evidence, 'reason': f'extended_above_ma20_{dist_ma20:.1f}%'}

        # MA60 distance gate (key grading indicator from empirical study)
        if dist_ma60 < min_pct_above_ma60:
            return False, {**evidence, 'reason': f'ma60_dist_{dist_ma60:.1f}%<{min_pct_above_ma60} (趋势未确立)'}
        if dist_ma60 > max_pct_above_ma60:
            return False, {**evidence, 'reason': f'ma60_dist_{dist_ma60:.1f}%>{max_pct_above_ma60} (过度乖离)'}

        if weeks_above is not None and weeks_above < min_weeks_above_ma20:
            return False, {**evidence, 'reason': f'weeks_above_ma20_{weeks_above}<{min_weeks_above_ma20}'}

        return True, evidence

    except Exception as e:
        return False, {'reason': f'error: {e}'}


def detect_pre_ignition(daily_df: pd.DataFrame,
                        weekly_df: pd.DataFrame = None,
                        pre_window_days: int = 10,
                        baseline_window_days: int = 20,
                        pre_return_min_pct: float = -5.0,
                        pre_return_max_pct: float = 15.0,
                        pre_vol_ratio_min: float = 1.0,
                        pre_vol_ratio_max: float = 2.0,
                        require_above_ma20: bool = True,
                        require_above_ma60: bool = True,
                        min_pct_from_60d_low: float = 5.0,
                        max_pct_from_60d_low: float = 50.0) -> tuple:
    """Track C — pre-ignition radar: stocks showing the empirical signature
    that preceded YTD ≥50% rallies in the 1-4 weeks before ignition.

    Empirical study (42 winners, 2026 H1) showed the consistent precursor:
      - Pre 10-day return: median +6.3%, range -5 to +15%
      - Pre 10-day volume / 20-day baseline: median 1.21x (range 1.0-2.0x)
      - Above MA20: 90% of winners
      - Above MA60: 93% of winners
      - Distance from 60-day low: median +25% (range +5% to +50%)

    This detector is **early-stage**, **broad recall** (~50%), **low precision**
    (~8%). Use it to populate an observation pool, NOT direct buy signals.

    Returns: (matched: bool, evidence: dict)
    """
    evidence = {}
    if daily_df is None or daily_df.empty or 'close' not in daily_df.columns:
        return False, {'reason': 'no_daily_data'}
    if len(daily_df) < 60:
        return False, {'reason': f'insufficient_days_{len(daily_df)}'}

    try:
        c = daily_df['close'].astype(float).reset_index(drop=True)
        v = daily_df['volume'].astype(float).reset_index(drop=True) if 'volume' in daily_df.columns else None
        cur = float(c.iloc[-1])

        # Pre-window return (last N days)
        if len(c) <= pre_window_days:
            return False, {'reason': 'insufficient_data_for_pre_window'}
        base_price = float(c.iloc[-(pre_window_days + 1)])
        pre_return = (cur / base_price - 1) * 100 if base_price > 0 else 0
        evidence['pre_return_pct'] = round(pre_return, 2)
        evidence['pre_window_days'] = pre_window_days

        # Pre-window volume vs baseline (20d ending pre_window days ago)
        pre_vol_ratio = None
        if v is not None and len(v) > pre_window_days + baseline_window_days:
            pre_vol = v.tail(pre_window_days).mean()
            base_vol = v.iloc[-(pre_window_days + baseline_window_days):-pre_window_days].mean()
            if base_vol > 0:
                pre_vol_ratio = float(pre_vol / base_vol)
        evidence['pre_vol_ratio'] = round(pre_vol_ratio, 2) if pre_vol_ratio is not None else None

        # MA positions
        ma20 = float(TechCalc.ma(c, 20).iloc[-1]) if len(c) >= 20 else 0
        ma60 = float(TechCalc.ma(c, 60).iloc[-1]) if len(c) >= 60 else 0
        above_ma20 = cur > ma20 if ma20 > 0 else False
        above_ma60 = cur > ma60 if ma60 > 0 else False
        evidence['ma20'] = round(ma20, 2)
        evidence['ma60'] = round(ma60, 2)
        evidence['above_ma20'] = above_ma20
        evidence['above_ma60'] = above_ma60

        # Distance from 60-day low
        low_60d = float(c.tail(60).min()) if len(c) >= 60 else float(c.min())
        pct_from_low = (cur / low_60d - 1) * 100 if low_60d > 0 else 0
        evidence['pct_from_60d_low'] = round(pct_from_low, 2)

        # Distance from 52w high (informational)
        hi_252 = float(c.tail(252).max() if len(c) >= 252 else c.max())
        pct_from_high = (1 - cur / hi_252) * 100 if hi_252 > 0 else 0
        evidence['pct_from_52w_high'] = round(pct_from_high, 2)

        # Apply gates
        if not (pre_return_min_pct <= pre_return <= pre_return_max_pct):
            return False, {**evidence, 'reason': f'pre_return_{pre_return:.1f}%_out_of_range'}

        if pre_vol_ratio is None:
            return False, {**evidence, 'reason': 'no_volume_baseline'}
        if not (pre_vol_ratio_min <= pre_vol_ratio <= pre_vol_ratio_max):
            return False, {**evidence, 'reason': f'pre_vol_{pre_vol_ratio:.2f}x_out_of_range'}

        if require_above_ma20 and not above_ma20:
            return False, {**evidence, 'reason': 'below_ma20'}
        if require_above_ma60 and not above_ma60:
            return False, {**evidence, 'reason': 'below_ma60'}

        if pct_from_low < min_pct_from_60d_low:
            return False, {**evidence, 'reason': f'too_close_to_low_{pct_from_low:.1f}%<{min_pct_from_60d_low}'}
        if pct_from_low > max_pct_from_60d_low:
            return False, {**evidence, 'reason': f'far_from_low_{pct_from_low:.1f}%>{max_pct_from_60d_low} (起涨已晚)'}

        return True, evidence

    except Exception as e:
        return False, {'reason': f'error: {e}'}


def derive_single_quarter(quarterly: list) -> list:
    """Convert Baostock cumulative quarterly data into single-quarter values.

    Baostock returns CUMULATIVE figures (Q1 / H1 / Q1-Q3 / Full Year).
    Single-quarter revenue / net_profit are derived by differencing within the
    same fiscal year.

    Caveat: Baostock often returns 0 (i.e. missing) for `MBRevenue` on Q1/Q3
    reports for some stocks, which causes huge negative or huge positive
    differences when naively subtracted. We therefore treat 0 as missing and
    skip the differencing for that metric in that quarter.

    Input: list of dicts (newest first) from StockDataProvider.get_quarterly_data():
        [{'period':'2024Q3','year':2024,'quarter':3,'revenue':100,'net_profit':10, ...}, ...]

    Returns: same list (newest first) with two extra keys per entry:
        'single_revenue': single-quarter revenue (亿元) or None
        'single_net_profit': single-quarter net profit (亿元) or None
    """
    if not quarterly:
        return []

    def _val(d: dict, key: str):
        """Treat 0 / None as missing (Baostock often returns 0 for missing fields)."""
        v = d.get(key, 0)
        if v is None or v == 0:
            return None
        try:
            return float(v)
        except Exception:
            return None

    by_period = {(q['year'], q['quarter']): q for q in quarterly}
    out = []
    for q in quarterly:
        y, qt = q['year'], q['quarter']
        single_rev = single_np = None
        try:
            cur_rev = _val(q, 'revenue')
            cur_np = _val(q, 'net_profit')
            if qt == 1:
                # Q1 cumulative == single-quarter
                single_rev = cur_rev
                single_np = cur_np
            else:
                prev = by_period.get((y, qt - 1))
                if prev is not None:
                    prev_rev = _val(prev, 'revenue')
                    prev_np = _val(prev, 'net_profit')
                    # Only difference when BOTH endpoints are valid (non-zero)
                    if cur_rev is not None and prev_rev is not None:
                        single_rev = cur_rev - prev_rev
                    if cur_np is not None and prev_np is not None:
                        single_np = cur_np - prev_np
        except Exception:
            pass
        out.append({**q, 'single_revenue': single_rev, 'single_net_profit': single_np})
    return out


def detect_qoq_first_improvement(quarterly: list,
                                 metrics: tuple = ('revenue', 'net_profit')) -> tuple:
    """Detect first-time YoY (year-over-year, same-quarter) improvement.

    Despite the legacy function name '_qoq_', this now compares the LATEST
    single-quarter value against the SAME quarter ONE YEAR AGO (e.g. 2026Q1
    vs 2025Q1). YoY removes seasonality. Pure sequential QoQ (Q1 vs Q4) was
    misleading for seasonal businesses (consumer electronics, retail, etc.)
    where Q1 is structurally weaker than Q4.

    "首次同比改善" = current single-quarter YoY > 0 AND the prior single
    quarter's YoY <= 0 AND current value > 0.

    Args:
        quarterly: list returned by derive_single_quarter() (newest first).
                   Need ≥6 entries to look back 1 year for two comparison points.
        metrics: which fields to check ('revenue', 'net_profit', or both).

    Returns: (matched: bool, evidence: dict)
    """
    evidence = {}
    if not quarterly or len(quarterly) < 6:
        n = len(quarterly) if quarterly else 0
        return False, {'reason': f'insufficient_quarterly_data_{n}<6'}

    # Build (year, quarter) -> entry map for fast YoY lookup
    by_period = {(q['year'], q['quarter']): q for q in quarterly}

    latest = quarterly[0]
    prev = quarterly[1]  # one quarter before latest

    y_l, q_l = latest['year'], latest['quarter']
    y_p, q_p = prev['year'], prev['quarter']

    yoy_latest_base = by_period.get((y_l - 1, q_l))
    yoy_prev_base = by_period.get((y_p - 1, q_p))

    evidence['latest_period'] = latest.get('period', '?')
    evidence['prev_period'] = prev.get('period', '?')
    evidence['yoy_latest_base_period'] = f"{y_l - 1}Q{q_l}"
    evidence['yoy_prev_base_period'] = f"{y_p - 1}Q{q_p}"

    if yoy_latest_base is None or yoy_prev_base is None:
        return False, {**evidence, 'reason': 'no_yoy_baseline'}

    matched_metric = None
    for metric in metrics:
        key = f'single_{metric}'
        cur = latest.get(key)
        cur_base = yoy_latest_base.get(key)
        prv = prev.get(key)
        prv_base = yoy_prev_base.get(key)

        if cur is None or cur_base is None or prv is None or prv_base is None:
            continue

        # Latest YoY % = (cur - same_quarter_last_year) / |same_quarter_last_year|
        if cur_base == 0:
            cur_yoy = float('inf') if cur > 0 else 0
        else:
            cur_yoy = (cur - cur_base) / abs(cur_base) * 100

        # Prior single-quarter YoY %
        if prv_base == 0:
            prv_yoy = float('inf') if prv > 0 else 0
        else:
            prv_yoy = (prv - prv_base) / abs(prv_base) * 100

        evidence[f'{metric}_latest_single'] = round(float(cur), 2)
        evidence[f'{metric}_yoy_base'] = round(float(cur_base), 2)
        evidence[f'{metric}_yoy_pct'] = (
            round(cur_yoy, 2) if cur_yoy != float('inf') else 999.99
        )
        evidence[f'{metric}_prev_yoy_pct'] = (
            round(prv_yoy, 2) if prv_yoy != float('inf') else 999.99
        )

        # First YoY improvement: latest YoY > 0 AND prior YoY <= 0 AND value > 0
        if cur > 0 and cur_yoy > 0 and prv_yoy <= 0:
            matched_metric = metric

    evidence['matched_metric'] = matched_metric
    return bool(matched_metric), evidence


def detect_cashflow_turn_positive(quarterly: list) -> tuple:
    """Detect operating cash flow turning positive vs prior period.

    Args:
        quarterly: list from StockDataProvider.get_quarterly_data() (newest first)
                   each entry has 'cfo_to_or' and 'cfo_positive' fields.

    Returns: (matched: bool, evidence: dict)
    """
    evidence = {}
    if not quarterly:
        return False, {'reason': 'no_quarterly_data'}

    latest = quarterly[0]
    cur_cfo = float(latest.get('cfo_to_or', 0) or 0)
    cur_pos = bool(latest.get('cfo_positive', False) or cur_cfo > 0)
    evidence['latest_period'] = latest.get('period', '?')
    evidence['latest_cfo_to_or'] = round(cur_cfo, 4)
    evidence['latest_cfo_positive'] = cur_pos

    if not cur_pos:
        return False, {**evidence, 'reason': 'latest_cfo_not_positive'}

    # Look at prior quarters (within same fiscal year ideally) to find a prior negative
    prior_negative = False
    for q in quarterly[1:4]:  # check up to 3 prior quarters
        pcfo = float(q.get('cfo_to_or', 0) or 0)
        if pcfo <= 0:
            prior_negative = True
            evidence['prior_negative_period'] = q.get('period', '?')
            evidence['prior_cfo_to_or'] = round(pcfo, 4)
            break

    evidence['turned_positive'] = prior_negative
    # "现金流转正": current positive AND at least one recent prior was negative
    return prior_negative, evidence


def detect_gross_margin_improvement(f: 'StockFinancials',
                                    history: list = None,
                                    min_improvement_pct: float = 1.0) -> tuple:
    """Detect year-over-year gross margin improvement.

    Gross margin (毛利率) is a leading indicator of profitability turnaround:
    cost relief, price hikes, product-mix upgrade all show up here BEFORE
    they hit net profit. A YoY improvement of >= min_improvement_pct points
    is treated as a positive signal.

    Args:
        f: latest StockFinancials (current gross_margin %)
        history: yearly history (newest first), each dict has 'gross_margin'
        min_improvement_pct: minimum YoY improvement in percentage points

    Returns: (matched: bool, evidence: dict)

    Note: Banks/insurance return 0 gross margin (no concept). Caller can choose
    to skip this signal for financials.
    """
    evidence = {}
    if f is None:
        return False, {'reason': 'no_financials'}

    cur_gm = float(getattr(f, 'gross_margin', 0) or 0)
    evidence['cur_gross_margin'] = round(cur_gm, 2)

    # Industries with no gross margin concept (banks, insurance) — skip
    if cur_gm <= 0:
        return False, {**evidence, 'reason': 'no_gross_margin_metric'}

    if not history or len(history) < 2:
        return False, {**evidence, 'reason': 'insufficient_history'}

    try:
        prev_gm = float(history[1].get('gross_margin', 0) or 0)
    except Exception:
        return False, {**evidence, 'reason': 'history_parse_error'}

    evidence['prev_gross_margin'] = round(prev_gm, 2)
    delta = cur_gm - prev_gm
    evidence['gross_margin_delta_pct'] = round(delta, 2)
    evidence['min_improvement_pct'] = min_improvement_pct

    matched = delta >= min_improvement_pct
    evidence['matched'] = bool(matched)
    return bool(matched), evidence


def check_fundamental_reversal(f: 'StockFinancials',
                               history: list = None,
                               quarterly: list = None,
                               profit_growth_turn_positive: bool = True,
                               roe_yoy_improvement_min: float = 0.0,
                               revenue_growth_min: float = -10.0,
                               check_qoq_improvement: bool = True,
                               check_cashflow_positive: bool = True,
                               check_gross_margin_improvement: bool = True,
                               gross_margin_min_improvement_pct: float = 1.0,
                               require_all: bool = False) -> tuple:
    """Check whether the latest financials show a fundamental reversal.

    Six signals (signals 4-5 require quarterly data, signal 6 requires history):
      1. Profit growth turn positive: latest profit_growth >= 0 AND prior year < 0
      2. ROE year-over-year improvement: latest ROE >= prior_year ROE + roe_yoy_improvement_min
      3. Revenue growth not collapsing: latest revenue_growth >= revenue_growth_min
      4. YoY first improvement (single-quarter): revenue or net_profit YoY turned positive
      5. Operating cash flow turned positive (latest > 0 AND prior period <= 0)
      6. Gross margin improvement YoY: latest gross_margin >= prev + min_improvement_pct
         (毛利率改善是利润反转的领先指标 — 成本/价格/产品结构变化先体现于此)

    history: yearly list from StockDataProvider.get_financial_history() (newest first)
    quarterly: quarterly list (already passed through derive_single_quarter()) — optional

    Returns: (matched: bool, evidence: dict)
    """
    evidence = {}
    if f is None:
        return False, {'reason': 'no_financials'}

    cur_pg = float(getattr(f, 'profit_growth', 0) or 0)
    cur_roe = float(getattr(f, 'roe', 0) or 0)
    cur_rg = float(getattr(f, 'revenue_growth', 0) or 0)
    evidence['cur_profit_growth'] = round(cur_pg, 2)
    evidence['cur_roe'] = round(cur_roe, 2)
    evidence['cur_revenue_growth'] = round(cur_rg, 2)

    prev_roe = None
    prev_pg = None
    if history and len(history) >= 2:
        # history[0] is latest; history[1] is one period prior
        try:
            prev_roe = float(history[1].get('roe', 0) or 0)
            prev_pg = float(history[1].get('profit_growth', 0) or 0)
            evidence['prev_roe'] = round(prev_roe, 2)
            evidence['prev_profit_growth'] = round(prev_pg, 2)
        except Exception:
            pass

    # Signal 1: profit growth turn positive
    sig1 = cur_pg >= 0 and (prev_pg is None or prev_pg < 0)
    evidence['signal_profit_turn_positive'] = bool(sig1)

    # Signal 2: ROE improvement YoY
    if prev_roe is not None:
        sig2 = (cur_roe - prev_roe) >= roe_yoy_improvement_min
    else:
        sig2 = cur_roe >= roe_yoy_improvement_min
    evidence['signal_roe_improving'] = bool(sig2)

    # Signal 3: revenue growth floor
    sig3 = cur_rg >= revenue_growth_min
    evidence['signal_revenue_floor'] = bool(sig3)

    # Signal 4: QoQ first improvement (requires quarterly data)
    sig4 = False
    if check_qoq_improvement and quarterly:
        ok4, ev4 = detect_qoq_first_improvement(quarterly)
        sig4 = ok4
        evidence['qoq_evidence'] = ev4
    evidence['signal_qoq_first_improvement'] = bool(sig4)

    # Signal 5: cash flow turned positive (requires quarterly data)
    sig5 = False
    if check_cashflow_positive and quarterly:
        ok5, ev5 = detect_cashflow_turn_positive(quarterly)
        sig5 = ok5
        evidence['cashflow_evidence'] = ev5
    evidence['signal_cashflow_turn_positive'] = bool(sig5)

    # Signal 6: gross margin YoY improvement (leading indicator)
    sig6 = False
    if check_gross_margin_improvement:
        ok6, ev6 = detect_gross_margin_improvement(
            f, history=history,
            min_improvement_pct=gross_margin_min_improvement_pct,
        )
        sig6 = ok6
        evidence['gm_evidence'] = ev6
    evidence['signal_gross_margin_improving'] = bool(sig6)

    # Combine
    if require_all:
        # Strict: all enabled signals must pass
        required = [sig3]  # revenue floor always required
        if profit_growth_turn_positive:
            required.append(sig1 or sig2)
        if check_qoq_improvement and quarterly:
            required.append(sig4)
        if check_cashflow_positive and quarterly:
            required.append(sig5)
        if check_gross_margin_improvement:
            required.append(sig6)
        matched = all(required)
    else:
        # Default (loose): revenue floor + at least one positive signal.
        # Signal 6 (gross margin) counts as a positive signal too.
        positive_signals = (
            int(sig1) + int(sig2) + int(sig4) + int(sig5) + int(sig6)
        )
        matched = sig3 and (positive_signals >= 1)
        if profit_growth_turn_positive:
            # Prefer sig1 (profit turn); accept sig4/sig5/sig6 as alt; or strong ROE (sig2)
            matched = sig3 and (
                sig1 or sig4 or sig5 or sig6 or (sig2 and cur_roe >= 8)
            )

    evidence['matched'] = bool(matched)
    return bool(matched), evidence

