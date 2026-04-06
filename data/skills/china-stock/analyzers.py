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
