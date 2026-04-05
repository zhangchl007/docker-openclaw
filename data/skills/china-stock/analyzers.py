#!/usr/bin/env python3
"""
Stock Analyzers - Pure Computation

这些分析器只做计算，不调用任何 API。
所有数据由 StockDataProvider 提供。
"""

import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict
from dataclasses import dataclass, asdict
from stock_data import StockQuote, StockFinancials


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
    """价值投资分析 (段永平/巴菲特)"""
    
    def analyze(self, q: StockQuote, f: StockFinancials, df: pd.DataFrame) -> AnalysisResult:
        scores = {}
        details = {}
        flags = []
        
        # ROE (0-25)
        roe = f.roe
        if roe >= 20:
            scores['roe'] = 25
        elif roe >= 15:
            scores['roe'] = 20
        elif roe >= 10:
            scores['roe'] = 15
        else:
            scores['roe'] = 5
            flags.append("低ROE")
        details['roe'] = f"ROE: {roe:.1f}%"
        
        # 利润率 (0-20)
        gm, nm = f.gross_margin, f.net_margin
        s = (10 if gm >= 40 else 6 if gm >= 25 else 2) + (10 if nm >= 15 else 6 if nm >= 8 else 2)
        scores['margin'] = s
        details['margin'] = f"毛利{gm:.1f}% 净利{nm:.1f}%"
        
        # 财务健康 (0-20)
        scores['health'] = 15  # 默认
        details['health'] = "财务稳健"
        
        # 估值 (0-20)
        pe = q.pe if q.pe > 0 else 20
        pb = q.pb if q.pb > 0 else 2
        pe_s = 10 if pe <= 15 else 7 if pe <= 25 else 4 if pe <= 40 else 1
        pb_s = 10 if pb <= 2 else 7 if pb <= 4 else 4 if pb <= 6 else 1
        scores['val'] = pe_s + pb_s
        details['val'] = f"PE:{pe:.1f} PB:{pb:.1f}"
        if pe > 40:
            flags.append("高PE")
        
        # 成长 (0-15)
        g = f.profit_growth
        if 20 <= g <= 50:
            scores['growth'] = 15
        elif g >= 10:
            scores['growth'] = 12
        elif g >= 0:
            scores['growth'] = 8
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
    """成长股分析 (彼得林奇)"""
    
    def analyze(self, q: StockQuote, f: StockFinancials, df: pd.DataFrame) -> AnalysisResult:
        scores = {}
        details = {}
        
        # PEG (0-30)
        pe = q.pe if q.pe > 0 else 20
        g = max(f.profit_growth, 1)
        peg = pe / g
        
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
    """综合分析 - 三种方法加权"""
    
    def __init__(self):
        self.canslim = CANSLIMAnalyzer()
        self.value = ValueAnalyzer()
        self.growth = GrowthAnalyzer()
        self.weights = {'canslim': 0.30, 'value': 0.35, 'growth': 0.35}
    
    def analyze(self, q: StockQuote, f: StockFinancials, df: pd.DataFrame) -> Dict:
        c = self.canslim.analyze(q, f, df)
        v = self.value.analyze(q, f, df)
        g = self.growth.analyze(q, f, df)
        
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
