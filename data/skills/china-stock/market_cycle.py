#!/usr/bin/env python3
"""
Market Cycle Analyzer - Howard Marks Framework (Data-Driven)
霍华德·马克斯市场周期评估 - 全部基于真实宏观数据

Data Sources (all from AKShare + Baostock):
- GDP, PMI, M2/M1 (经济数据)
- 国债收益率, 中美利差 (利率环境)
- 融资融券余额 (杠杆水平)
- 上证/沪深300/创业板 (市场表现)
- 人民币汇率 (资本流动)
- IPO数量, 回购金额 (市场供给)
- 成交量, 波动率 (投资者情绪)
"""

import json
import time
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List
from dataclasses import dataclass, asdict

import akshare as ak
from stock_data import get_provider


@dataclass
class CycleDimension:
    name: str
    label_high: str
    label_low: str
    score: float        # -1 to +1
    evidence: str
    data_point: str


class MacroDataCollector:
    """Collect real macro data from AKShare + Baostock"""

    def __init__(self):
        self.provider = get_provider()
        self._api_calls = 0

    def _safe_call(self, func, name, *args, **kwargs):
        """Safe API call with retry"""
        try:
            self._api_calls += 1
            result = func(*args, **kwargs)
            time.sleep(0.3)
            return result
        except Exception as e:
            print(f"  [!] {name} failed: {e}")
            return None

    def collect_all(self) -> Dict:
        """Collect all macro data"""
        data = {}
        t0 = time.time()

        # 1. GDP
        print("  [1/12] GDP...")
        df = self._safe_call(ak.macro_china_gdp, 'GDP')
        if df is not None and not df.empty:
            latest = df.iloc[0]
            data['gdp'] = {
                'period': str(latest['季度']),
                'growth': float(latest.get('国内生产总值-同比增长', 0) or 0),
            }

        # 2. PMI
        print("  [2/12] PMI...")
        df = self._safe_call(ak.macro_china_pmi, 'PMI')
        if df is not None and not df.empty:
            latest = df.iloc[0]
            data['pmi'] = {
                'period': str(latest['月份']),
                'manufacturing': float(latest.get('制造业-指数', 0) or 0),
                'non_manufacturing': float(latest.get('非制造业-指数', 0) or 0),
            }

        # 3. M2/M1
        print("  [3/12] M2/M1...")
        df = self._safe_call(ak.macro_china_money_supply, 'M2')
        if df is not None and not df.empty:
            latest = df.iloc[0]
            data['money'] = {
                'period': str(latest['月份']),
                'm2_yoy': float(latest.get('货币和准货币(M2)-同比增长', 0) or 0),
                'm1_yoy': float(latest.get('货币(M1)-同比增长', 0) or 0),
            }

        # 4. 国债收益率 + 中美利差
        print("  [4/12] 国债收益率...")
        start = (datetime.now() - timedelta(days=400)).strftime('%Y%m%d')
        end = datetime.now().strftime('%Y%m%d')
        df = self._safe_call(ak.bond_zh_us_rate, '国债')
        if df is not None and not df.empty:
            latest = df.iloc[-1]
            year_ago = df.iloc[-252] if len(df) > 252 else df.iloc[0]
            data['bond'] = {
                'cn_10y': float(latest.get('中国国债收益率10年', 0) or 0),
                'cn_10y_1y_ago': float(year_ago.get('中国国债收益率10年', 0) or 0),
                'us_10y': float(latest.get('美国国债收益率10年', 0) or 0),
                'spread': float((latest.get('中国国债收益率10年', 0) or 0) - (latest.get('美国国债收益率10年', 0) or 0)),
                'cn_2y_10y': float(latest.get('中国国债收益率10年-2年', 0) or 0),
            }

        # 5. 融资融券
        print("  [5/12] 融资融券...")
        df = self._safe_call(ak.stock_margin_sse, '融资',
                             start_date=(datetime.now() - timedelta(days=400)).strftime('%Y%m%d'),
                             end_date=datetime.now().strftime('%Y%m%d'))
        if df is not None and not df.empty:
            latest = df.iloc[-1]
            earliest = df.iloc[0]
            margin_bal = float(latest.get('融资余额', 0) or 0)
            margin_bal_prev = float(earliest.get('融资余额', 0) or 0)
            data['margin'] = {
                'balance': margin_bal,
                'balance_bn': margin_bal / 1e9,
                'change_pct': ((margin_bal / margin_bal_prev) - 1) * 100 if margin_bal_prev > 0 else 0,
            }

        # 6. 汇率
        print("  [6/12] 人民币汇率...")
        df = self._safe_call(ak.currency_boc_sina, '汇率', symbol='美元',
                             start_date=(datetime.now() - timedelta(days=60)).strftime('%Y%m%d'),
                             end_date=datetime.now().strftime('%Y%m%d'))
        if df is not None and not df.empty:
            latest_rate = float(df.iloc[0].get('央行中间价', 0) or 0) / 100
            earliest_rate = float(df.iloc[-1].get('央行中间价', 0) or 0) / 100
            data['fx'] = {
                'usdcny': latest_rate,
                'change_pct': ((latest_rate / earliest_rate) - 1) * 100 if earliest_rate > 0 else 0,
            }

        # 7. IPO节奏
        print("  [7/12] IPO...")
        df = self._safe_call(ak.stock_ipo_info, 'IPO')
        if df is not None and not df.empty:
            # Count 2026 IPOs
            try:
                year_str = str(datetime.now().year)
                count = len(df)  # All current IPOs in pipeline
                data['ipo'] = {'count_current': count}
            except:
                data['ipo'] = {'count_current': 0}

        # 8. 回购
        print("  [8/12] 回购...")
        df = self._safe_call(ak.stock_repurchase_em, '回购')
        if df is not None and not df.empty:
            # Count recent (last 3 months)
            try:
                recent = df[df['回购起始时间'] >= (datetime.now() - timedelta(days=90)).date()]
                total_amount = recent['计划回购金额区间-下限'].sum()
                data['buyback'] = {
                    'count_90d': len(recent),
                    'amount_bn': float(total_amount) / 1e9 if total_amount else 0,
                }
            except:
                data['buyback'] = {'count_90d': 0, 'amount_bn': 0}

        # 9-11. Index data (from Baostock, already cached)
        print("  [9/12] 上证指数...")
        sh = self.provider.get_history('000001', 365)
        if not sh.empty:
            c = sh['close']
            v = sh['volume']
            data['sh_index'] = {
                'current': float(c.iloc[-1]),
                'change_1y': float((c.iloc[-1] / c.iloc[0] - 1) * 100),
                'pct_from_high': float((c.iloc[-1] / c.max() - 1) * 100),
                'pct_from_low': float((c.iloc[-1] / c.min() - 1) * 100),
                'vol_ratio_20d_1y': float(v.iloc[-20:].mean() / v.mean()) if len(v) >= 20 else 1,
                'up_days_20': int((sh['pctChg'].iloc[-20:] > 0).sum()) if len(sh) >= 20 else 10,
            }
            # Volatility
            ret = c.pct_change().dropna()
            data['sh_index']['volatility_20d'] = float(ret.iloc[-20:].std() * np.sqrt(252) * 100) if len(ret) >= 20 else 20

        print("  [10/12] 沪深300...")
        csi = self.provider.get_history('000300', 365)
        if not csi.empty:
            c = csi['close']
            data['csi300'] = {
                'current': float(c.iloc[-1]),
                'change_1y': float((c.iloc[-1] / c.iloc[0] - 1) * 100),
                'pct_from_high': float((c.iloc[-1] / c.max() - 1) * 100),
                'pct_from_low': float((c.iloc[-1] / c.min() - 1) * 100),
            }

        print("  [11/12] 创业板...")
        chinext = self.provider.get_history('399006', 365)
        if not chinext.empty:
            c = chinext['close']
            data['chinext'] = {
                'current': float(c.iloc[-1]),
                'change_1y': float((c.iloc[-1] / c.iloc[0] - 1) * 100),
            }

        # 12. LPR
        print("  [12/12] LPR...")
        df = self._safe_call(ak.macro_china_lpr, 'LPR')
        if df is not None and not df.empty:
            # Find latest non-NaN row
            for _, row in df.iterrows():
                try:
                    lpr1y = float(row.get('LPR1Y', 0) or 0)
                    lpr5y = float(row.get('LPR5Y', 0) or 0)
                    if lpr1y > 0:
                        data['lpr'] = {'lpr_1y': lpr1y, 'lpr_5y': lpr5y}
                        break
                except:
                    continue

        elapsed = time.time() - t0
        data['_meta'] = {
            'timestamp': datetime.now().isoformat(),
            'api_calls': self._api_calls,
            'elapsed_seconds': round(elapsed, 1),
        }
        print(f"  Data collection done: {self._api_calls} calls, {elapsed:.1f}s")

        return data


class MarketCycleAnalyzer:
    """Howard Marks 14-dimension cycle assessment with real data"""

    def __init__(self):
        self.collector = MacroDataCollector()
        self.cache_path = Path('/home/node/.openclaw/stock-data/cache/macro_data.json')
        self.manual_path = Path('/home/node/.openclaw/stock-data/market-cycle.json')

    def _load_cache(self, ttl_hours: int = 4) -> Dict:
        if self.cache_path.exists():
            try:
                with open(self.cache_path) as f:
                    cached = json.load(f)
                ts = datetime.fromisoformat(cached.get('_meta', {}).get('timestamp', '2000-01-01'))
                if datetime.now() - ts < timedelta(hours=ttl_hours):
                    return cached
            except:
                pass
        return {}

    def _save_cache(self, data: Dict):
        try:
            with open(self.cache_path, 'w') as f:
                json.dump(data, f, ensure_ascii=False, default=str)
        except:
            pass

    def _load_manual(self) -> Dict:
        if self.manual_path.exists():
            try:
                with open(self.manual_path) as f:
                    return json.load(f)
            except:
                pass
        return {}

    def analyze(self) -> Dict:
        """Run full cycle analysis"""
        print("[Cycle] Starting market cycle analysis...")

        # Try cache first
        data = self._load_cache(ttl_hours=4)
        if data:
            print("[Cycle] Using cached macro data")
        else:
            print("[Cycle] Fetching fresh macro data...")
            data = self.collector.collect_all()
            self._save_cache(data)

        manual = self._load_manual()
        dims = []

        # ===== 1. 经济现状 (GDP + PMI) =====
        gdp_g = data.get('gdp', {}).get('growth', 5)
        pmi = data.get('pmi', {}).get('manufacturing', 50)
        if gdp_g >= 6 and pmi >= 52:
            s = 0.8
        elif gdp_g >= 5 and pmi >= 50.5:
            s = 0.3
        elif gdp_g >= 4.5 and pmi >= 49.5:
            s = 0
        elif gdp_g >= 4 or pmi >= 48:
            s = -0.3
        else:
            s = -0.8
        dims.append(CycleDimension(
            "经济现状", "生机勃勃", "停滞不前", s,
            "GDP + PMI",
            f"GDP:{gdp_g:.1f}% PMI:{pmi:.1f}"
        ))

        # ===== 2. 经济展望 (国债收益率曲线) =====
        spread_2_10 = data.get('bond', {}).get('cn_2y_10y', 0.5)
        cn_10y = data.get('bond', {}).get('cn_10y', 2)
        cn_10y_ago = data.get('bond', {}).get('cn_10y_1y_ago', 2)
        if spread_2_10 > 0.8:
            s = 0.5  # Steep curve = optimistic outlook
        elif spread_2_10 > 0.3:
            s = 0.2
        elif spread_2_10 > 0:
            s = -0.2
        else:
            s = -0.7  # Inverted = recession signal
        dims.append(CycleDimension(
            "经济展望", "正面有利", "负面不利", s,
            "国债收益率曲线(2Y-10Y利差)",
            f"10Y:{cn_10y:.2f}% 2Y-10Y利差:{spread_2_10:.2f}% 10Y一年前:{cn_10y_ago:.2f}%"
        ))

        # ===== 3. 贷款机构 (M2增速 + 融资余额变化) =====
        m2_yoy = data.get('money', {}).get('m2_yoy', 8)
        margin_chg = data.get('margin', {}).get('change_pct', 0)
        if m2_yoy >= 10 and margin_chg > 10:
            s = 0.8
        elif m2_yoy >= 8:
            s = 0.4
        elif m2_yoy >= 6:
            s = 0
        else:
            s = -0.5
        margin_bn = data.get('margin', {}).get('balance_bn', 0)
        dims.append(CycleDimension(
            "贷款机构", "急于放贷", "缄默谨慎", s,
            "M2增速 + 融资余额",
            f"M2同比:{m2_yoy:.1f}% 融资余额:{margin_bn:.0f}亿 变化:{margin_chg:+.1f}%"
        ))

        # ===== 4. 资本市场 (M2 + M1剪刀差) =====
        m1_yoy = data.get('money', {}).get('m1_yoy', 5)
        m2_m1 = m2_yoy - m1_yoy  # M2-M1 gap: large gap = funds idle, not investing
        if m2_m1 < 1:
            s = 0.7  # M1 catching up = capital active
        elif m2_m1 < 3:
            s = 0.3
        elif m2_m1 < 5:
            s = 0
        else:
            s = -0.5  # Large gap = capital hoarding
        dims.append(CycleDimension(
            "资本市场", "宽松", "紧缩", s,
            "M2-M1剪刀差",
            f"M2:{m2_yoy:.1f}% M1:{m1_yoy:.1f}% 剪刀差:{m2_m1:.1f}%"
        ))

        # ===== 5. 资本供给 (成交量) =====
        vol_ratio = data.get('sh_index', {}).get('vol_ratio_20d_1y', 1)
        if vol_ratio > 1.5:
            s = 0.8
        elif vol_ratio > 1.1:
            s = 0.3
        elif vol_ratio > 0.8:
            s = 0
        else:
            s = -0.5
        dims.append(CycleDimension(
            "资本供给", "充足", "短缺", s,
            "上证成交量(20日/年均)",
            f"量比:{vol_ratio:.2f}"
        ))

        # ===== 6. 融资条款 (融资余额 + IPO + 回购) =====
        ipo_count = data.get('ipo', {}).get('count_current', 0)
        buyback_count = data.get('buyback', {}).get('count_90d', 0)
        buyback_amt = data.get('buyback', {}).get('amount_bn', 0)
        # High IPO + low buyback = easy financing; Low IPO + high buyback = tight
        if ipo_count > 30 and buyback_count < 100:
            s = 0.7
        elif ipo_count > 15:
            s = 0.3
        elif ipo_count <= 10 and buyback_count > 300:
            s = -0.5
        else:
            s = 0
        dims.append(CycleDimension(
            "融资条款", "宽松", "严格", s,
            "IPO数量 + 回购",
            f"IPO在审:{ipo_count} 近90天回购:{buyback_count}家/{buyback_amt:.0f}亿"
        ))

        # ===== 7. 利率水平 =====
        lpr_1y = data.get('lpr', {}).get('lpr_1y', 3.5)
        cn_10y_val = data.get('bond', {}).get('cn_10y', 2.5)
        if cn_10y_val < 2.0:
            s = 0.8  # Very low rates
        elif cn_10y_val < 2.5:
            s = 0.4
        elif cn_10y_val < 3.0:
            s = 0
        elif cn_10y_val < 3.5:
            s = -0.3
        else:
            s = -0.7
        us_10y = data.get('bond', {}).get('us_10y', 4)
        spread = data.get('bond', {}).get('spread', -2)
        dims.append(CycleDimension(
            "利率水平", "低(刺激)", "高(收紧)", s,
            "10Y国债 + 中美利差",
            f"中10Y:{cn_10y_val:.2f}% 美10Y:{us_10y:.2f}% 利差:{spread:+.2f}%"
        ))

        # ===== 8. 投资人情绪 (涨跌天数 + 波动率) =====
        up_days = data.get('sh_index', {}).get('up_days_20', 10)
        volatility = data.get('sh_index', {}).get('volatility_20d', 20)
        if up_days >= 14 and volatility < 20:
            s = 0.8  # Very optimistic
        elif up_days >= 12:
            s = 0.4
        elif up_days >= 8:
            s = 0
        elif up_days >= 6:
            s = -0.3
        else:
            s = -0.7  # Very pessimistic
        dims.append(CycleDimension(
            "投资人", "乐观/自信", "悲观/忧虑", s,
            "近20日涨跌比 + 波动率",
            f"涨:{up_days}天 跌:{20-up_days}天 波动率:{volatility:.1f}%"
        ))

        # ===== 9. 资产持有人 (汇率走势 = 外资流向proxy) =====
        fx_chg = data.get('fx', {}).get('change_pct', 0)
        usdcny = data.get('fx', {}).get('usdcny', 7)
        if fx_chg < -1:
            s = 0.5  # CNY strengthening = capital inflow
        elif fx_chg < 0:
            s = 0.2
        elif fx_chg < 1:
            s = 0
        else:
            s = -0.5  # CNY weakening = capital outflow
        dims.append(CycleDimension(
            "资产持有人", "乐观持有(资本流入)", "悲观卖出(资本流出)", s,
            "人民币汇率走势",
            f"USD/CNY:{usdcny:.2f} 近期变化:{fx_chg:+.2f}%"
        ))

        # ===== 10. 基金 (成交量趋势 as proxy) =====
        # Use volume trend over 3 months
        if vol_ratio > 1.3:
            s = 0.6
        elif vol_ratio > 1.0:
            s = 0.2
        elif vol_ratio > 0.7:
            s = -0.2
        else:
            s = -0.6
        dims.append(CycleDimension(
            "基金", "申购门槛高/新品频发", "开放/难募资", s,
            "市场成交量趋势",
            f"量比:{vol_ratio:.2f} (>1=活跃 <1=冷清)"
        ))

        # ===== 11. 近期业绩 =====
        csi_chg = data.get('csi300', {}).get('change_1y', 0)
        cn_chg = data.get('chinext', {}).get('change_1y', 0)
        avg_chg = (csi_chg + cn_chg) / 2
        if avg_chg > 20:
            s = 0.8
        elif avg_chg > 10:
            s = 0.5
        elif avg_chg > 0:
            s = 0.2
        elif avg_chg > -10:
            s = -0.2
        elif avg_chg > -20:
            s = -0.5
        else:
            s = -0.8
        dims.append(CycleDimension(
            "近期业绩", "强劲", "萎靡", s,
            "沪深300 + 创业板年涨跌",
            f"沪深300:{csi_chg:+.1f}% 创业板:{cn_chg:+.1f}%"
        ))

        # ===== 12. 资产价格 =====
        pct_high = data.get('csi300', {}).get('pct_from_high', 0)
        pct_low = data.get('csi300', {}).get('pct_from_low', 0)
        position = pct_low / (pct_low - pct_high) if (pct_low - pct_high) != 0 else 0.5
        if position > 0.85:
            s = 0.8
        elif position > 0.65:
            s = 0.3
        elif position > 0.35:
            s = 0
        elif position > 0.15:
            s = -0.3
        else:
            s = -0.8
        dims.append(CycleDimension(
            "资产价格", "高", "低", s,
            "沪深300 52周位置",
            f"距高:{pct_high:.1f}% 距低:+{pct_low:.1f}% 位置:{position*100:.0f}%"
        ))

        # ===== 13. 预期收益 (inverse of price) =====
        er = -s
        dims.append(CycleDimension(
            "预期收益", "低(高价=低回报)", "高(低价=高回报)", er,
            "资产价格反向",
            f"{'预期收益偏低' if er > 0 else '预期收益偏高'}"
        ))

        # ===== 14. 流行风格 =====
        # High vol + high volume + up market = aggressive style popular
        sh_chg = data.get('sh_index', {}).get('change_1y', 0)
        if sh_chg > 15 and vol_ratio > 1.2:
            s = 0.7
        elif sh_chg > 5:
            s = 0.3
        elif sh_chg > -5:
            s = 0
        else:
            s = -0.5
        dims.append(CycleDimension(
            "流行风格 vs 正确风格",
            "激进/四处投资(应谨慎)", "谨慎/极挑细选(应激进)", s,
            "市场涨幅 + 成交活跃度",
            f"上证年涨跌:{sh_chg:+.1f}% 量比:{vol_ratio:.2f}"
        ))

        # ===== Total Score =====
        total = sum(d.score for d in dims)
        max_score = len(dims)

        # Cycle position
        if total >= 8:
            pos, emoji, rec = "⚠️ 周期高位 — 极度乐观", "🔴🔴🔴", "极度谨慎！减仓/防守为主。市场过度乐观时，聪明的投资者应该恐惧。"
        elif total >= 4:
            pos, emoji, rec = "⚠️ 周期偏高 — 乐观情绪升温", "🟠🟠", "适当减仓，提高现金比例，避免追高。"
        elif total >= 1:
            pos, emoji, rec = "📊 周期中部偏高", "🟡", "持有优质资产，不宜过度加仓。"
        elif total >= -1:
            pos, emoji, rec = "📊 周期中部 — 中性", "⚪", "正常配置，保持纪律。"
        elif total >= -4:
            pos, emoji, rec = "✅ 周期中部偏低", "🟢", "关注机会，逐步建仓优质资产。"
        elif total >= -8:
            pos, emoji, rec = "✅ 周期偏低 — 悲观蔓延", "🟢🟢", "积极买入！别人恐惧时贪婪。"
        else:
            pos, emoji, rec = "✅ 周期低位 — 极度悲观", "🟢🟢🟢", "千载难逢！全力加仓优质资产。"

        return {
            'timestamp': datetime.now().isoformat(),
            'total_score': total,
            'max_score': max_score,
            'position': pos,
            'emoji': emoji,
            'recommendation': rec,
            'dimensions': [asdict(d) for d in dims],
            'market_data': data,
        }

    def _generate_advice(self, result: Dict) -> List[str]:
        """Generate comprehensive investment advice based on real data"""
        lines = []
        data = result['market_data']
        total = result['total_score']
        dims = {d['name']: d for d in result['dimensions']}

        # --- 1. Core Contradiction ---
        lines.append("### 🔍 核心矛盾分析")
        lines.append("")

        bullish = []
        bearish = []
        for d in result['dimensions']:
            if d['score'] >= 0.4:
                bullish.append(f"{d['name']}({d['data_point']})")
            elif d['score'] <= -0.4:
                bearish.append(f"{d['name']}({d['data_point']})")

        if bullish:
            lines.append("**利好信号:**")
            for b in bullish:
                lines.append(f"- 🟠 {b}")
        if bearish:
            lines.append("**利空信号:**")
            for b in bearish:
                lines.append(f"- 🟢 {b}")
        if not bullish and not bearish:
            lines.append("- 市场信号均处于中性区域，无明显方向")
        lines.append("")

        # --- 2. Monetary Environment ---
        lines.append("### 💵 货币与利率环境")
        lines.append("")

        cn_10y = data.get('bond', {}).get('cn_10y', 2.5)
        us_10y = data.get('bond', {}).get('us_10y', 4)
        spread = data.get('bond', {}).get('spread', -1.5)
        m2 = data.get('money', {}).get('m2_yoy', 8)
        m1 = data.get('money', {}).get('m1_yoy', 5)
        m2_m1 = m2 - m1

        if cn_10y < 2.0:
            lines.append(f'- 中国10Y国债{cn_10y:.2f}%处于**历史极低水平**，"资产荒"格局明显，资金被迫寻找高收益资产')
            lines.append(f"- 低利率利好股市估值，但也反映经济增长预期偏弱")
        elif cn_10y < 2.5:
            lines.append(f"- 中国10Y国债{cn_10y:.2f}%偏低，流动性较充裕")
        else:
            lines.append(f"- 中国10Y国债{cn_10y:.2f}%处于正常水平")

        if spread < -2:
            lines.append(f"- ⚠️ 中美利差{spread:+.2f}%严重倒挂(中{cn_10y:.2f}% vs 美{us_10y:.2f}%)，人民币承压，外资流出压力大")
        elif spread < 0:
            lines.append(f"- 中美利差{spread:+.2f}%倒挂，关注汇率波动风险")

        if m2_m1 > 4:
            lines.append(f"- M2-M1剪刀差{m2_m1:.1f}%(M2:{m2:.1f}% M1:{m1:.1f}%)偏大，资金沉淀在储蓄中未进入实体，经济活力不足")
        elif m2_m1 < 2:
            lines.append(f"- M2-M1剪刀差{m2_m1:.1f}%收窄，资金活化，经济活力提升")
        else:
            lines.append(f"- M2:{m2:.1f}% M1:{m1:.1f}%，货币环境适中")
        lines.append("")

        # --- 3. Market Valuation ---
        lines.append("### 📊 市场估值与位置")
        lines.append("")

        sh_chg = data.get('sh_index', {}).get('change_1y', 0)
        sh_cur = data.get('sh_index', {}).get('current', 0)
        sh_high = data.get('sh_index', {}).get('pct_from_high', 0)
        csi_chg = data.get('csi300', {}).get('change_1y', 0)
        cn_chg = data.get('chinext', {}).get('change_1y', 0)

        lines.append(f"- 上证指数 {sh_cur:.0f}点，年涨{sh_chg:+.1f}%，距52周高点{sh_high:.1f}%")
        lines.append(f"- 沪深300年涨{csi_chg:+.1f}%，创业板年涨{cn_chg:+.1f}%")

        if cn_chg > 50:
            lines.append(f"- ⚠️ **创业板年涨{cn_chg:.0f}%涨幅过大**，已透支较多未来收益，短期追高风险大")
        if csi_chg > 20 and cn_chg > 40:
            lines.append(f"- 大小盘齐涨，市场处于普涨阶段后期，分化可能加剧")
        elif csi_chg < 5 and cn_chg > 30:
            lines.append(f"- 创业板远超沪深300，风格极度偏向成长/小盘，注意风格切换风险")

        margin_chg = data.get('margin', {}).get('change_pct', 0)
        margin_bn = data.get('margin', {}).get('balance_bn', 0)
        if margin_chg < -15:
            lines.append(f'- ⚠️ 融资余额{margin_bn:.0f}亿，较年初下降{abs(margin_chg):.0f}%，杠杆资金在撤退——市场涨但杠杆降，"聪明钱"在减仓')
        elif margin_chg > 20:
            lines.append(f"- 融资余额{margin_bn:.0f}亿大幅增长{margin_chg:.0f}%，杠杆升温，需警惕")
        lines.append("")

        # --- 4. Position & Strategy ---
        lines.append("### 🎯 仓位与策略建议")
        lines.append("")

        if total >= 8:
            lines.append("| 项目 | 建议 |")
            lines.append("|------|------|")
            lines.append("| 仓位 | ⚠️ 降至30-40%，大幅提高现金 |")
            lines.append("| 操作 | 逢高减仓，不追涨 |")
            lines.append("| 风格 | 纯防御：高分红、低估值蓝筹 |")
            lines.append("| 忌讳 | 杠杆、追热点、高估值 |")
        elif total >= 4:
            lines.append("| 项目 | 建议 |")
            lines.append("|------|------|")
            lines.append("| 仓位 | 降至50-60%，增加现金储备 |")
            lines.append("| 操作 | 减持涨幅过大品种，锁定利润 |")
            lines.append("| 风格 | 偏防御：蓝筹+高分红 |")
            lines.append("| 关注 | 回调后的优质品种加仓机会 |")
        elif total >= 1:
            lines.append("| 项目 | 建议 |")
            lines.append("|------|------|")
            lines.append("| 仓位 | 维持60-70%，保留现金应对波动 |")
            lines.append("| 操作 | 持有优质资产，不追涨不杀跌 |")
            lines.append("| 风格 | 均衡配置：成长+价值 |")
            lines.append("| 关注 | 精选个股，避免普涨思维 |")
        elif total >= -1:
            lines.append("| 项目 | 建议 |")
            lines.append("|------|------|")
            lines.append("| 仓位 | 70-80%正常配置 |")
            lines.append("| 操作 | 按纪律操作，定投 |")
            lines.append("| 风格 | 均衡 |")
        elif total >= -4:
            lines.append("| 项目 | 建议 |")
            lines.append("|------|------|")
            lines.append("| 仓位 | 逐步加仓至80%+ |")
            lines.append("| 操作 | 分批买入优质资产 |")
            lines.append("| 风格 | 偏进攻：优质成长+被低估龙头 |")
            lines.append("| 关注 | 恐慌中寻找被错杀的好公司 |")
        else:
            lines.append("| 项目 | 建议 |")
            lines.append("|------|------|")
            lines.append("| 仓位 | ✅ 全力加仓至90%+ |")
            lines.append("| 操作 | 大胆买入，别人恐惧时贪婪 |")
            lines.append("| 风格 | 进攻：龙头+弹性品种 |")
            lines.append("| 机会 | 历史性机会，重仓优质资产 |")
        lines.append("")

        # --- 5. Sector Advice ---
        lines.append("### 📁 板块配置建议")
        lines.append("")

        if cn_10y < 2.0:
            lines.append("- **高分红/类债资产**: 利率极低下，银行、公用事业、高速公路等高分红股吸引力提升")
        if cn_chg > 40:
            lines.append("- **创业板/科技**: 涨幅已大，谨慎对待高估值科技股，精选有真实业绩的龙头")
        else:
            lines.append("- **科技/成长**: 关注有真实业绩增长的细分龙头")

        if data.get('pmi', {}).get('manufacturing', 50) > 50:
            lines.append("- **制造业/周期**: PMI在扩张区间，关注受益于经济复苏的周期品种")
        else:
            lines.append("- **消费/医药**: PMI在收缩区间，偏向防御性消费和医药")

        buyback_ct = data.get('buyback', {}).get('count_90d', 0)
        if buyback_ct > 150:
            lines.append(f"- **回购活跃板块**: 近90天{buyback_ct}家公司回购，关注回购金额大的个股(管理层对估值有信心)")
        lines.append("")

        # --- 6. Risk Warnings ---
        lines.append("### ⚠️ 风险提示")
        lines.append("")

        risks = []
        if spread < -2:
            risks.append(f"中美利差倒挂{spread:+.1f}%，人民币贬值和外资流出风险")
        if cn_chg > 60:
            risks.append(f"创业板年涨{cn_chg:.0f}%，估值泡沫化风险")
        if margin_chg < -20:
            risks.append(f"融资余额下降{abs(margin_chg):.0f}%，杠杆资金撤退信号")
        if data.get('sh_index', {}).get('volatility_20d', 0) > 30:
            risks.append("市场波动率偏高，注意控制仓位")
        if data.get('pmi', {}).get('manufacturing', 50) < 49:
            risks.append("PMI低于荣枯线，经济收缩风险")
        if data.get('gdp', {}).get('growth', 5) < 4.5:
            risks.append(f"GDP增速{data['gdp']['growth']:.1f}%偏低，基本面支撑不足")

        if risks:
            for r in risks:
                lines.append(f"- {r}")
        else:
            lines.append("- 当前无重大系统性风险信号，但需保持警惕")
        lines.append("")

        # --- 7. Howard Marks Quote ---
        lines.append("### 📖 大师箴言")
        lines.append("")
        if total >= 4:
            lines.append('> **"在市场高位时，大多数人看到的是机会，少数人看到的是风险。"** 周期的关键在于：当所有人都乐观时，价格已反映了所有好消息，剩下的只有坏消息的风险。 — 霍华德·马克斯')
        elif total <= -4:
            lines.append('> **"最好的投资交易，来自于所有人都想逃离的时候。"** 当恐惧弥漫市场，优质资产被以白菜价抛售，这正是长期投资者的黄金时刻。 — 霍华德·马克斯')
        else:
            lines.append('> **"我们不需要预测未来，只需要知道我们在周期中的位置。"** 当前处于中部区域，最重要的是保持纪律，不因贪婪或恐惧而偏离策略。 — 霍华德·马克斯')

        return lines

    def format_report(self, result: Dict) -> str:
        """Format as markdown"""
        lines = []
        total = result['total_score']
        max_s = result['max_score']

        lines.append("# 🔄 霍华德·马克斯 市场周期评估")
        lines.append(f"**全部基于真实宏观数据 | {datetime.now():%Y-%m-%d %H:%M}**")
        lines.append("")

        # Position
        lines.append(f"## {result['emoji']} {result['position']}")
        lines.append(f"**综合得分: {total:+.1f} / ±{max_s}** (正=高位风险 / 负=低位机会)")
        lines.append("")

        # Gauge
        norm = (total + max_s) / (2 * max_s)
        pos = max(0, min(29, int(norm * 30)))
        bar = list("─" * 30)
        bar[pos] = "●"
        lines.append(f"```")
        lines.append(f"恐惧 ◀ {''.join(bar)} ▶ 贪婪")
        lines.append(f"得分: {total:+.1f}")
        lines.append(f"```")
        lines.append("")

        # Recommendation
        lines.append(f"> 💡 **{result['recommendation']}**")
        lines.append("")

        # Dimensions table
        lines.append("## 📊 14维度评估")
        lines.append("")
        lines.append("| # | 维度 | 高位 ◀ | 得分 | ▶ 低位 | 数据依据 |")
        lines.append("|---|------|--------|------|--------|----------|")

        for i, d in enumerate(result['dimensions'], 1):
            sc = d['score']
            if sc > 0.3:
                indicator = "🟠◀"
            elif sc < -0.3:
                indicator = "▶🟢"
            else:
                indicator = "⚪"
            lines.append(f"| {i} | {d['name']} | {d['label_high']} | {indicator} {sc:+.1f} | {d['label_low']} | {d['data_point']} |")

        lines.append("")

        # Key data summary
        data = result['market_data']
        lines.append("## 📈 关键宏观数据")
        lines.append("")

        lines.append("| 指标 | 数值 | 含义 |")
        lines.append("|------|------|------|")

        gdp = data.get('gdp', {})
        if gdp:
            lines.append(f"| GDP增速 | {gdp.get('growth', 0):.1f}% ({gdp.get('period', '')}) | {'强劲' if gdp.get('growth',0) >= 5.5 else '温和' if gdp.get('growth',0) >= 4.5 else '放缓'} |")

        pmi = data.get('pmi', {})
        if pmi:
            val = pmi.get('manufacturing', 50)
            lines.append(f"| 制造业PMI | {val:.1f} ({pmi.get('period', '')}) | {'扩张' if val > 50 else '收缩'} |")

        money = data.get('money', {})
        if money:
            lines.append(f"| M2同比 | {money.get('m2_yoy', 0):.1f}% | {'宽松' if money.get('m2_yoy',0) > 9 else '适中' if money.get('m2_yoy',0) > 7 else '偏紧'} |")
            lines.append(f"| M1同比 | {money.get('m1_yoy', 0):.1f}% | {'资金活跃' if money.get('m1_yoy',0) > 8 else '正常' if money.get('m1_yoy',0) > 3 else '资金沉淀'} |")

        bond = data.get('bond', {})
        if bond:
            lines.append(f"| 中国10Y国债 | {bond.get('cn_10y', 0):.2f}% | {'极低' if bond.get('cn_10y',0) < 2 else '偏低' if bond.get('cn_10y',0) < 2.5 else '正常'} |")
            lines.append(f"| 美国10Y国债 | {bond.get('us_10y', 0):.2f}% | 中美利差:{bond.get('spread', 0):+.2f}% |")

        margin = data.get('margin', {})
        if margin:
            lines.append(f"| 融资余额 | {margin.get('balance_bn', 0):.0f}亿 | 变化:{margin.get('change_pct', 0):+.1f}% |")

        fx = data.get('fx', {})
        if fx:
            lines.append(f"| USD/CNY | {fx.get('usdcny', 0):.2f} | {'升值' if fx.get('change_pct',0) < 0 else '贬值'}:{fx.get('change_pct',0):+.2f}% |")

        buyback = data.get('buyback', {})
        if buyback:
            lines.append(f"| 近90天回购 | {buyback.get('count_90d', 0)}家/{buyback.get('amount_bn', 0):.0f}亿 | {'活跃' if buyback.get('count_90d',0) > 200 else '正常'} |")

        ipo = data.get('ipo', {})
        if ipo:
            lines.append(f"| IPO在审 | {ipo.get('count_current', 0)}家 | {'偏多' if ipo.get('count_current',0) > 30 else '正常' if ipo.get('count_current',0) > 10 else '收紧'} |")

        sh = data.get('sh_index', {})
        if sh:
            lines.append(f"| 上证指数 | {sh.get('current', 0):.0f} | 年涨跌:{sh.get('change_1y', 0):+.1f}% |")
            lines.append(f"| 20日波动率 | {sh.get('volatility_20d', 0):.1f}% | {'高波动' if sh.get('volatility_20d',0) > 30 else '正常'} |")

        lines.append("")
        
        # ===== Investment Advice Section =====
        lines.append("## 💰 综合投资建议")
        lines.append("")
        lines.extend(self._generate_advice(result))
        lines.append("")

        lines.append("---")
        meta = data.get('_meta', {})
        lines.append(f"*数据源: AKShare + Baostock | API调用: {meta.get('api_calls', 0)} | 耗时: {meta.get('elapsed_seconds', 0)}s*")
        lines.append("*基于霍华德·马克斯《周期》(Mastering the Market Cycle)*")

        return '\n'.join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Market Cycle Analysis')
    parser.add_argument('--output', type=str, help='Output file')
    parser.add_argument('--send', action='store_true', help='Send to WeChat')
    parser.add_argument('--refresh', action='store_true', help='Force refresh data')
    parser.add_argument('--biweekly', action='store_true', help='Only run on even weeks (for cron)')
    args = parser.parse_args()

    # Biweekly check: only run on even ISO weeks (2,4,6,8...)
    if args.biweekly:
        week_num = datetime.now().isocalendar()[1]
        if week_num % 2 != 0:
            print(f"[Cycle] Skipping: week {week_num} is odd (biweekly mode)")
            return

    analyzer = MarketCycleAnalyzer()

    if args.refresh:
        # Clear cache
        try:
            analyzer.cache_path.unlink()
        except:
            pass

    try:
        result = analyzer.analyze()
        report = analyzer.format_report(result)

        if args.send:
            from notifier import Notifier
            n = Notifier()
            r = n.send_all(report, "🔄 市场周期评估")
            print(json.dumps(r, ensure_ascii=False, indent=2))
        elif args.output:
            with open(args.output, 'w') as f:
                f.write(report)
            print(f"Saved to {args.output}")
        else:
            print(report)
    finally:
        analyzer.collector.provider.cleanup()


if __name__ == '__main__':
    main()
