#!/usr/bin/env python3
"""
Deep-Dive Stock Analysis Report Generator

Generates professional-grade analysis reports with:
- Technical indicators (MA, RSI, MACD, Bollinger Bands)
- Fundamental metrics (PE, PB, ROE, PEG, margins)
- Three-master scoring (CANSLIM, Value, Growth)
- Position & risk commentary
- Actionable insights
"""

import json
import time
import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from stock_data import get_provider, StockQuote, StockFinancials
from analyzers import MasterAnalyzer, TechCalc


class DeepDiveReport:
    """Professional deep-dive report generator"""

    def __init__(self):
        self.provider = get_provider()
        self.analyzer = MasterAnalyzer()
        self.watchlist_file = Path('/home/node/.openclaw/stock-data/watchlist.json')

    def load_watchlist(self) -> Dict:
        if self.watchlist_file.exists():
            with open(self.watchlist_file) as f:
                return json.load(f)
        return {'groups': {}}

    # ==================== Technical Indicators ====================

    def calc_technicals(self, df: pd.DataFrame) -> Dict:
        """Calculate comprehensive technical indicators from daily data"""
        if df.empty or 'close' not in df.columns:
            return {}

        c = df['close'].dropna()
        if len(c) < 20:
            return {}

        cur = c.iloc[-1]
        prev = c.iloc[-2] if len(c) > 1 else cur

        # Moving Averages
        ma5 = TechCalc.ma(c, 5).iloc[-1]
        ma10 = TechCalc.ma(c, 10).iloc[-1]
        ma20 = TechCalc.ma(c, 20).iloc[-1]
        ma60 = TechCalc.ma(c, 60).iloc[-1] if len(c) >= 60 else None

        # RSI
        rsi = TechCalc.rsi(c, 14)

        # MACD
        ema12 = c.ewm(span=12).mean()
        ema26 = c.ewm(span=26).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9).mean()
        macd_hist = macd_line - signal_line
        macd_val = float(macd_line.iloc[-1])
        macd_sig = float(signal_line.iloc[-1])
        macd_h = float(macd_hist.iloc[-1])

        # Bollinger Bands
        bb_mid = ma20
        bb_std = c.rolling(20).std().iloc[-1]
        bb_upper = bb_mid + 2 * bb_std
        bb_lower = bb_mid - 2 * bb_std
        bb_width = (bb_upper - bb_lower) / bb_mid * 100
        bb_position = (cur - bb_lower) / (bb_upper - bb_lower) * 100 if (bb_upper - bb_lower) > 0 else 50

        # Volume analysis
        vol = df['volume'].dropna() if 'volume' in df.columns else pd.Series()
        vol_ratio = float(vol.iloc[-5:].mean() / vol.rolling(20).mean().iloc[-1]) if len(vol) >= 20 else 1

        # Volatility (20-day)
        returns = c.pct_change()
        volatility = float(returns.rolling(20).std().iloc[-1] * np.sqrt(252) * 100) if len(returns) > 20 else 0

        # Price position
        high_52w = c.max()
        low_52w = c.min()
        pct_from_high = (cur / high_52w - 1) * 100
        pct_from_low = (cur / low_52w - 1) * 100

        # Trend
        if cur > ma5 > ma10 > ma20:
            trend = "强势上涨"
            trend_emoji = "📈📈"
        elif cur > ma20:
            trend = "震荡偏强"
            trend_emoji = "📈"
        elif cur < ma5 < ma10 < ma20:
            trend = "弱势下跌"
            trend_emoji = "📉📉"
        elif cur < ma20:
            trend = "震荡偏弱"
            trend_emoji = "📉"
        else:
            trend = "横盘整理"
            trend_emoji = "➡️"

        # MA Support/Resistance
        support = min(ma5, ma10, ma20)
        resistance = max(ma5, ma10, ma20)

        return {
            'price': cur,
            'ma5': ma5, 'ma10': ma10, 'ma20': ma20, 'ma60': ma60,
            'rsi': rsi,
            'macd': macd_val, 'macd_signal': macd_sig, 'macd_hist': macd_h,
            'bb_upper': bb_upper, 'bb_lower': bb_lower, 'bb_width': bb_width, 'bb_position': bb_position,
            'vol_ratio': vol_ratio,
            'volatility': volatility,
            'high_52w': high_52w, 'low_52w': low_52w,
            'pct_from_high': pct_from_high, 'pct_from_low': pct_from_low,
            'trend': trend, 'trend_emoji': trend_emoji,
            'support': support, 'resistance': resistance,
        }

    # ==================== Deep Dive Per Stock ====================

    def deep_dive_stock(self, code: str, name: str, q: StockQuote, f: StockFinancials, df: pd.DataFrame) -> str:
        """Generate deep-dive analysis for a single stock"""

        # Run three-master analysis
        master = self.analyzer.analyze(q, f, df)

        # Calculate technicals
        tech = self.calc_technicals(df)

        # Fetch multi-year financial history
        fin_history = self.provider.get_financial_history(code)

        lines = []

        # Header
        lines.append(f"### {name} ({code})")
        chg_emoji = "🟢" if q.change_pct >= 0 else "🔴"
        lines.append(f"**价格:** ¥{q.price:.2f} ({chg_emoji}{q.change_pct:+.2f}%) | **评分:** {master['master_score']:.1f}/100 | {master['master_emoji']} **{master['master_rating']}**")
        lines.append("")

        # === Key Metrics Table ===
        lines.append("**📊 核心指标:**")
        lines.append("")
        lines.append("| 指标 | 数值 | 评价 |")
        lines.append("|------|------|------|")

        # PE
        pe = q.pe
        pe_judge = "低估" if pe > 0 and pe < 20 else "合理" if pe <= 35 else "偏高" if pe <= 60 else "高估" if pe > 0 else "N/A"
        lines.append(f"| PE(TTM) | {pe:.1f} | {pe_judge} |")

        # PB
        pb = q.pb
        pb_judge = "低估" if pb > 0 and pb < 2 else "合理" if pb <= 4 else "偏高" if pb <= 8 else "高估" if pb > 0 else "N/A"
        lines.append(f"| PB | {pb:.2f} | {pb_judge} |")

        # ROE
        roe = f.roe
        roe_judge = "优秀" if roe >= 20 else "良好" if roe >= 15 else "一般" if roe >= 10 else "较低" if roe >= 5 else "差"
        lines.append(f"| ROE | {roe:.1f}% | {roe_judge} |")

        # PEG
        growth = max(f.profit_growth, 0.1)
        peg = pe / growth if pe > 0 and growth > 0 else 0
        peg_judge = "极佳" if 0 < peg <= 0.5 else "偏低" if peg <= 1 else "合理" if peg <= 1.5 else "偏高" if peg <= 2 else "过高" if peg > 0 else "N/A"
        lines.append(f"| PEG | {peg:.2f} | {peg_judge} |")

        # Margins
        lines.append(f"| 毛利率 | {f.gross_margin:.1f}% | {'高' if f.gross_margin >= 40 else '中' if f.gross_margin >= 20 else '低'} |")
        lines.append(f"| 净利率 | {f.net_margin:.1f}% | {'高' if f.net_margin >= 15 else '中' if f.net_margin >= 5 else '低'} |")

        # Growth
        pg_judge = "高增长" if f.profit_growth >= 25 else "稳增长" if f.profit_growth >= 10 else "低增长" if f.profit_growth >= 0 else "负增长"
        lines.append(f"| 利润增长 | {f.profit_growth:.1f}% | {pg_judge} |")
        lines.append(f"| 营收增长 | {f.revenue_growth:.1f}% | {'正' if f.revenue_growth > 0 else '负'} |")
        lines.append("")

        # === Multi-Year Financial History ===
        if fin_history and len(fin_history) >= 3:
            is_hk = str(code).startswith('hk')
            years_label = f"{'9' if is_hk else '10'}年" 
            lines.append(f"**📈 {years_label}财务趋势:**")
            lines.append("")
            lines.append("| 年份 | ROE | 毛利率 | 净利率 | 营收增 | 净利增 |")
            lines.append("|------|-----|--------|--------|--------|--------|")

            for h in fin_history:
                yr = h.get('year', '')[:4]
                roe_v = h.get('roe', 0)
                gm_v = h.get('gross_margin', 0)
                nm_v = h.get('net_margin', 0)
                rg_v = h.get('revenue_growth', 0)
                pg_v = h.get('profit_growth', 0)
                lines.append(f"| {yr} | {roe_v:.1f}% | {gm_v:.1f}% | {nm_v:.1f}% | {rg_v:+.1f}% | {pg_v:+.1f}% |")

            lines.append("")

            # Trend analysis from history
            roe_vals = [h['roe'] for h in fin_history if h.get('roe', 0) != 0]
            gm_vals = [h['gross_margin'] for h in fin_history if h.get('gross_margin', 0) != 0]
            pg_vals = [h['profit_growth'] for h in fin_history]

            if len(roe_vals) >= 3:
                roe_peak = max(roe_vals)
                roe_now = roe_vals[0] if roe_vals else 0
                roe_avg = sum(roe_vals) / len(roe_vals)
                recent_2 = sum(roe_vals[:2]) / 2 if len(roe_vals) >= 2 else roe_now
                older_2 = sum(roe_vals[-2:]) / 2 if len(roe_vals) >= 2 else roe_vals[-1]

                lines.append("**🔍 周期分析:**")

                # ROE trend
                if recent_2 > older_2 * 1.1:
                    lines.append(f"- ROE趋势 📈 **向上** (近期{recent_2:.1f}% vs 早期{older_2:.1f}%)")
                elif recent_2 < older_2 * 0.7:
                    lines.append(f"- ROE趋势 📉 **下滑** (近期{recent_2:.1f}% vs 早期{older_2:.1f}%，峰值{roe_peak:.1f}%)")
                else:
                    lines.append(f"- ROE趋势 ➡️ **稳定** (均值{roe_avg:.1f}%)")

                # Cycle position
                if roe_now < roe_avg * 0.6 and roe_now > 0:
                    lines.append(f"- 📌 当前ROE {roe_now:.1f}%远低于均值{roe_avg:.1f}%，可能处于**周期底部**")
                elif roe_now > roe_avg * 1.3:
                    lines.append(f"- ⚠️ 当前ROE {roe_now:.1f}%高于均值{roe_avg:.1f}%，可能处于**周期高位**")

                # Margin trend
                if len(gm_vals) >= 3:
                    gm_now = gm_vals[0]
                    gm_avg = sum(gm_vals) / len(gm_vals)
                    if gm_now < gm_avg * 0.8:
                        lines.append(f"- ⚠️ 毛利率{gm_now:.1f}%低于均值{gm_avg:.1f}%，竞争优势可能在收窄")
                    elif gm_now > gm_avg * 1.1:
                        lines.append(f"- ✅ 毛利率{gm_now:.1f}%高于均值{gm_avg:.1f}%，定价权增强")

                # Growth stability
                if len(pg_vals) >= 5:
                    neg_years = sum(1 for p in pg_vals if p < 0)
                    if neg_years == 0:
                        lines.append(f"- ✅ 近{len(pg_vals)}年利润无负增长，增长质量优秀")
                    elif neg_years >= 3:
                        lines.append(f"- ⚠️ 近{len(pg_vals)}年中有{neg_years}年负增长，业绩波动大")

                lines.append("")

        # === Technical Analysis ===
        if tech:
            lines.append(f"**📈 技术分析:** {tech['trend_emoji']} {tech['trend']}")
            lines.append("")
            lines.append("| 指标 | 数值 | 信号 |")
            lines.append("|------|------|------|")

            # RSI
            rsi = tech['rsi']
            rsi_sig = "超买" if rsi > 70 else "超卖" if rsi < 30 else "中性"
            lines.append(f"| RSI(14) | {rsi:.1f} | {rsi_sig} |")

            # MACD
            macd_sig = "金叉(看多)" if tech['macd_hist'] > 0 else "死叉(看空)"
            lines.append(f"| MACD | {tech['macd']:.3f} | {macd_sig} |")

            # Bollinger
            bb_sig = "超买区" if tech['bb_position'] > 80 else "超卖区" if tech['bb_position'] < 20 else "中间区域"
            lines.append(f"| 布林位置 | {tech['bb_position']:.0f}% | {bb_sig} |")

            # Volume
            vr = tech['vol_ratio']
            vr_sig = "放量" if vr >= 1.5 else "缩量" if vr < 0.7 else "正常"
            lines.append(f"| 量比 | {vr:.2f} | {vr_sig} |")

            # Volatility
            lines.append(f"| 年化波动率 | {tech['volatility']:.1f}% | {'高' if tech['volatility'] > 40 else '中' if tech['volatility'] > 25 else '低'} |")
            lines.append("")

            # Position
            lines.append(f"**价格位置:** 距52周高 {tech['pct_from_high']:.1f}% / 距52周低 +{tech['pct_from_low']:.1f}%")
            lines.append(f"**均线支撑:** MA5=¥{tech['ma5']:.2f} MA10=¥{tech['ma10']:.2f} MA20=¥{tech['ma20']:.2f}" + (f" MA60=¥{tech['ma60']:.2f}" if tech['ma60'] else ""))
            lines.append("")

        # === Three-Master Scores ===
        lines.append("**🏆 三大师评分:**")
        lines.append("")
        lines.append("| 分析方法 | 评分 | 评级 | 核心观点 |")
        lines.append("|----------|------|------|----------|")

        for key, label in [('canslim', 'CANSLIM'), ('value', '价值投资'), ('growth', '成长分析')]:
            a = master[key]
            detail_items = a.get('details', {}).get('details', {})
            # Pick top 2 most relevant details
            top_details = list(detail_items.values())[:2]
            insight = " / ".join(top_details) if top_details else ""
            lines.append(f"| {label} | {a['score']:.0f}/{a['max_score']} | {a['emoji']} {a['rating']} | {insight} |")

        lines.append("")

        # === Investment Commentary ===
        lines.append("**💡 投资点评:**")
        lines.append("")
        commentary = self._generate_commentary(name, q, f, tech, master, fin_history)
        for line in commentary:
            lines.append(line)
        lines.append("")

        return '\n'.join(lines)

    def _generate_commentary(self, name: str, q: StockQuote, f: StockFinancials, tech: Dict, master: Dict, fin_history: List[Dict] = None) -> List[str]:
        """Generate investment commentary based on data"""
        comments = []

        # Valuation
        pe = q.pe
        if pe > 100:
            comments.append(f"- ⚠️ **估值警告**: PE {pe:.1f}倍偏高，需高增长支撑，否则有回调风险")
        elif pe > 50:
            comments.append(f"- ⚠️ PE {pe:.1f}倍处于较高水平，关注业绩增速能否匹配")
        elif 0 < pe <= 20:
            comments.append(f"- ✅ PE {pe:.1f}倍处于合理偏低区间，估值有安全边际")

        # Growth quality
        if f.profit_growth > 50:
            comments.append(f"- ✅ **高增长**: 利润同比增长{f.profit_growth:.1f}%，成长性优异")
        elif f.profit_growth < -20:
            comments.append(f"- ⚠️ **利润下滑**: 同比下降{abs(f.profit_growth):.1f}%，关注基本面恶化风险")
        elif f.profit_growth < 0:
            comments.append(f"- 📌 利润同比下降{abs(f.profit_growth):.1f}%，需关注后续季度能否改善")

        # ROE
        if f.roe >= 20:
            comments.append(f"- ✅ ROE {f.roe:.1f}%优秀，显示强竞争壁垒(段永平最看重)")
        elif f.roe < 5 and f.roe > 0:
            comments.append(f"- ⚠️ ROE仅{f.roe:.1f}%，资本回报率偏低")

        # Gross margin (moat indicator)
        if f.gross_margin >= 60:
            comments.append(f"- ✅ 毛利率{f.gross_margin:.1f}%，护城河宽广")
        elif f.gross_margin >= 40:
            comments.append(f"- 📌 毛利率{f.gross_margin:.1f}%，具有一定定价权")

        # Technical
        if tech:
            if tech['rsi'] > 70:
                comments.append(f"- ⚠️ RSI {tech['rsi']:.0f}超买，短期注意回调")
            elif tech['rsi'] < 30:
                comments.append(f"- 📌 RSI {tech['rsi']:.0f}超卖，可能存在反弹机会")

            if '下跌' in tech['trend']:
                comments.append(f"- ⚠️ 技术面偏弱，均线空头排列，等待企稳信号")
            elif '上涨' in tech['trend']:
                comments.append(f"- ✅ 技术面强势，均线多头排列，趋势向好")

        # PEG (Lynch's favorite)
        growth = max(f.profit_growth, 0.1)
        peg = pe / growth if pe > 0 and growth > 0 else 0
        if 0 < peg <= 1:
            comments.append(f"- ✅ PEG {peg:.2f} < 1，彼得·林奇标准下被低估")
        elif peg > 2 and pe > 0:
            comments.append(f"- ⚠️ PEG {peg:.2f}偏高，成长性不足以支撑估值")

        # Multi-year history insights
        if fin_history and len(fin_history) >= 5:
            roe_vals = [h['roe'] for h in fin_history if h.get('roe', 0) != 0]
            gm_vals = [h['gross_margin'] for h in fin_history if h.get('gross_margin', 0) != 0]

            if len(roe_vals) >= 5:
                roe_now = roe_vals[0]
                roe_peak = max(roe_vals)
                roe_avg = sum(roe_vals) / len(roe_vals)

                # Buffett/Duan Yongping perspective
                if roe_now >= 15 and all(r >= 12 for r in roe_vals[:5]):
                    comments.append(f"- 💎 **段永平标准**: ROE连续5年>12%(均值{roe_avg:.1f}%)，优质生意")
                elif roe_now < roe_peak * 0.4 and roe_peak >= 15:
                    comments.append(f"- 📌 **周期底部信号**: 当前ROE {roe_now:.1f}%仅为峰值{roe_peak:.1f}%的{roe_now/roe_peak*100:.0f}%，若行业回暖可关注")

            # Margin stability (moat durability)
            if len(gm_vals) >= 5:
                gm_std = (sum((g - sum(gm_vals)/len(gm_vals))**2 for g in gm_vals) / len(gm_vals)) ** 0.5
                if gm_std < 3:
                    comments.append(f"- ✅ 毛利率{len(gm_vals)}年波动仅{gm_std:.1f}%，护城河极稳定")
                elif gm_std > 10:
                    comments.append(f"- ⚠️ 毛利率{len(gm_vals)}年波动{gm_std:.1f}%，竞争格局不稳定")

        if not comments:
            comments.append(f"- 📌 该股基本面数据有限，建议进一步研究后再做决策")

        return comments

    # ==================== Full Report ====================

    def generate(self, sector: str = None) -> str:
        """Generate the full deep-dive report"""
        t0 = time.time()
        self.provider.reset_stats()

        wl = self.load_watchlist()

        if sector and sector in wl.get('groups', {}):
            sectors = {sector: wl['groups'][sector]}
        else:
            sectors = wl.get('groups', {})

        if not sectors:
            return "没有股票"

        # Collect all codes
        all_codes = []
        for stocks in sectors.values():
            for s in stocks:
                all_codes.append(s['code'] if isinstance(s, dict) else s)

        # Prefetch
        print(f"[Report] Prefetching {len(all_codes)} stocks...")
        self.provider.prefetch(all_codes)

        # Get quotes
        quotes = self.provider.get_quotes(all_codes)

        # Build report
        lines = []
        lines.append(f"# 📊 深度分析报告")
        lines.append(f"**生成时间:** {datetime.now().strftime('%Y-%m-%d %H:%M')} | **数据源:** 腾讯财经 + Baostock")
        lines.append("")

        # Overview table
        all_results = []
        for sec_name, stocks in sectors.items():
            for s in stocks:
                code = s['code'] if isinstance(s, dict) else s
                name = s.get('name', code) if isinstance(s, dict) else code
                q = quotes.get(code, StockQuote(code=code))
                q.name = name
                f = self.provider.get_financials(code)
                df = self.provider.get_history(code)
                master = self.analyzer.analyze(q, f, df)
                all_results.append((sec_name, code, name, q, f, df, master))

        # Sort by score
        all_results.sort(key=lambda x: x[6]['master_score'], reverse=True)

        # Summary table
        lines.append("## 🏆 综合排名")
        lines.append("")
        lines.append("| # | 股票 | 价格 | 涨跌 | PE | PB | ROE | 评分 | 评级 |")
        lines.append("|---|------|------|------|----|----|-----|------|------|")

        for i, (sec, code, name, q, f, df, m) in enumerate(all_results, 1):
            chg = f"{'🟢' if q.change_pct >= 0 else '🔴'}{q.change_pct:+.2f}%"
            lines.append(f"| {i} | {name} | ¥{q.price:.2f} | {chg} | {q.pe:.1f} | {q.pb:.2f} | {f.roe:.1f}% | {m['master_score']:.1f} | {m['master_emoji']} {m['master_rating']} |")

        lines.append("")

        # Sector deep dives
        current_sector = None
        for sec, code, name, q, f, df, m in all_results:
            if sec != current_sector:
                lines.append(f"## 📁 {sec}")
                lines.append("")
                current_sector = sec

            lines.append(self.deep_dive_stock(code, name, q, f, df))
            lines.append("---")
            lines.append("")

        # Footer
        elapsed = time.time() - t0
        lines.append(f"*分析方法: CANSLIM(欧奈尔) + 价值投资(段永平/巴菲特) + 成长分析(彼得·林奇)*")
        lines.append(f"*生成用时: {elapsed:.2f}s | API调用: {self.provider.api_calls}*")

        return '\n'.join(lines)


def main():
    import argparse

    parser = argparse.ArgumentParser(description='深度分析报告')
    parser.add_argument('--sector', type=str, help='指定板块')
    parser.add_argument('--output', type=str, help='输出文件')
    args = parser.parse_args()

    report = DeepDiveReport()

    try:
        output = report.generate(sector=args.sector)

        if args.output:
            with open(args.output, 'w') as f:
                f.write(output)
            print(f"报告已保存: {args.output}")
        else:
            print(output)
    finally:
        report.provider.cleanup()


if __name__ == '__main__':
    main()
