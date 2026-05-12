#!/usr/bin/env python3
"""
Screener Report Formatter

Builds two outputs from MarketScreener.run() result:
  1. Full markdown report (saved to reports/screen-{ts}.md)
  2. Compact WeChat summary (Top N per track)
"""

from datetime import datetime
from typing import Dict, List


def _fmt_money(yi: float) -> str:
    if yi is None:
        return "-"
    if yi >= 10000:
        return f"{yi/10000:.2f}万亿"
    if yi >= 1:
        return f"{yi:.1f}亿"
    return f"{yi*10000:.0f}万"


def _track_a_table_row(c: Dict) -> str:
    ev = c.get('evidence') or {}
    fr = c.get('fund_reversal') or {}
    consec = ev.get('consec_high_vol_weeks', '-')
    pct_low = ev.get('pct_from_low', '-')
    pct_high = ev.get('pct_from_high', '-')
    avg_ratio = ev.get('avg_vol_ratio', '-')
    pg_turn = '✅' if fr.get('signal_profit_turn_positive') else '➖'
    roe_imp = '✅' if fr.get('signal_roe_improving') else '➖'
    qoq = '✅' if fr.get('signal_qoq_first_improvement') else '➖'
    cf = '✅' if fr.get('signal_cashflow_turn_positive') else '➖'
    gm = '✅' if fr.get('signal_gross_margin_improving') else '➖'
    fund_pass = '✅' if c.get('fund_reversal_passed') else '⚠️'
    # Score: show raw → adjusted if different
    raw = c.get('master_score_raw', c.get('master_score', 0))
    adj = c.get('master_score', 0)
    if abs(raw - adj) >= 0.5:
        score_cell = f"{c['canslim_score']:.0f}/{raw:.0f}→{adj:.0f}"
    else:
        score_cell = f"{c['canslim_score']:.0f}/{adj:.0f}"
    return (
        f"| {c['code']} | {c['name']} | {c.get('industry','-')[:8]} | "
        f"¥{c['price']:.2f} | {c['change_pct']:+.2f}% | "
        f"{consec}周 | {avg_ratio} | {pct_low}% | {pct_high}% | "
        f"{fund_pass} {pg_turn}/{roe_imp}/{qoq}/{cf}/{gm} | "
        f"{score_cell} | "
        f"{c.get('master_emoji','')} {c.get('master_rating','')} |"
    )


def _track_b_table_row(c: Dict) -> str:
    ev = c.get('evidence') or {}
    pct_high = ev.get('pct_from_high', '-')
    rs = ev.get('relative_strength', '-')
    pct_ma60 = ev.get('pct_above_ma60', '-')
    vol_ratio = ev.get('vol_5d_vs_20d', '-')
    above_ma = ev.get('weeks_above_w_ma20', '-')
    return (
        f"| {c['code']} | {c['name']} | {c.get('industry','-')[:8]} | "
        f"¥{c['price']:.2f} | {c['change_pct']:+.2f}% | "
        f"-{pct_high}% | {rs} | +{pct_ma60}% | {vol_ratio}x | {above_ma}周 | "
        f"{c['canslim_score']:.0f}/{c['master_score']:.0f} | "
        f"{c.get('master_emoji','')} {c.get('master_rating','')} |"
    )


def _why_a(c: Dict) -> str:
    ev = c.get('evidence') or {}
    fr = c.get('fund_reversal') or {}
    parts = []
    parts.append(
        f"价格距52周低 +{ev.get('pct_from_low','-')}%, 距52周高 -{ev.get('pct_from_high','-')}%"
    )
    parts.append(
        f"周线连续 {ev.get('consec_high_vol_weeks','-')} 周量比≥{ev.get('avg_vol_ratio','-')}x, "
        f"周振幅均值 {ev.get('avg_weekly_range_pct','-')}%"
    )
    fund_bits = []
    if fr.get('signal_profit_turn_positive'):
        fund_bits.append(
            f"净利同比由 {fr.get('prev_profit_growth','?')}% 转 {fr.get('cur_profit_growth','?')}%"
        )
    if fr.get('signal_roe_improving'):
        fund_bits.append(
            f"ROE 由 {fr.get('prev_roe','?')}% → {fr.get('cur_roe','?')}%"
        )
    if fr.get('signal_revenue_floor'):
        fund_bits.append(f"营收增速 {fr.get('cur_revenue_growth','?')}% (未崩塌)")
    # Signal 4: YoY first improvement (function name kept '_qoq_' for backward compat)
    qev = fr.get('qoq_evidence') or {}
    if fr.get('signal_qoq_first_improvement') and qev.get('matched_metric'):
        m = qev['matched_metric']
        latest = qev.get('latest_period', '?')
        yoy_base = qev.get('yoy_latest_base_period', '?')
        cur_yoy = qev.get(f'{m}_yoy_pct', '?')
        prev_yoy = qev.get(f'{m}_prev_yoy_pct', '?')
        zh = '营收' if m == 'revenue' else '净利'
        fund_bits.append(
            f"{latest} 单季{zh}同比首次转正 (vs {yoy_base}): "
            f"上期 {prev_yoy}% → 本期 {cur_yoy}%"
        )
    # Signal 5: cashflow turn positive
    cev = fr.get('cashflow_evidence') or {}
    if fr.get('signal_cashflow_turn_positive'):
        latest = cev.get('latest_period', '?')
        prior = cev.get('prior_negative_period', '?')
        fund_bits.append(f"经营现金流 {prior} 负 → {latest} 转正 (CFO/营收={cev.get('latest_cfo_to_or','?')})")
    # Signal 6: gross margin YoY improvement
    gev = fr.get('gm_evidence') or {}
    if fr.get('signal_gross_margin_improving'):
        prev_gm = gev.get('prev_gross_margin', '?')
        cur_gm = gev.get('cur_gross_margin', '?')
        delta = gev.get('gross_margin_delta_pct', '?')
        fund_bits.append(f"毛利率同比提升 {prev_gm}% → {cur_gm}% (+{delta}pct, 利润领先指标)")
    if fund_bits:
        parts.append("基本面: " + "; ".join(fund_bits))
    elif not c.get('fund_reversal_passed'):
        parts.append("基本面反转: ⚠️未触发 (依靠技术面底部资金御号, 走势领先财报)"
        )
    # Score adjustments transparency
    adj = c.get('score_adjustments') or {}
    raw = c.get('master_score_raw', c.get('master_score', 0))
    final = c.get('master_score', 0)
    if adj:
        delta_str = ', '.join(f"{k} {v:+.0f}" for k, v in adj.items())
        parts.append(f"评分 CANSLIM={c['canslim_score']:.0f} Value={c['value_score']:.0f} "
                     f"Growth={c['growth_score']:.0f} Master={raw:.1f}→**{final:.1f}** ({delta_str})")
    else:
        parts.append(
            f"评分 CANSLIM={c['canslim_score']:.0f} Value={c['value_score']:.0f} "
            f"Growth={c['growth_score']:.0f} Master={final:.1f}"
        )
    return "  - " + "\n  - ".join(parts)


def _why_b(c: Dict) -> str:
    ev = c.get('evidence') or {}
    parts = []
    parts.append(f"距52周高 -{ev.get('pct_from_high','-')}% (临近新高)")
    parts.append(
        f"相对强度 RS={ev.get('relative_strength','-')}, "
        f"5/20日量比 {ev.get('vol_5d_vs_20d','-')}x"
    )
    parts.append(
        f"均线 MA5={ev.get('ma5','-')} > MA10={ev.get('ma10','-')} > MA20={ev.get('ma20','-')}, "
        f"价格高于MA20 {ev.get('pct_above_ma20','-')}%"
    )
    if ev.get('weeks_above_w_ma20') is not None:
        parts.append(f"周线已站上 MA20 共 {ev.get('weeks_above_w_ma20')} 周")
    parts.append(
        f"评分 CANSLIM={c['canslim_score']:.0f} Value={c['value_score']:.0f} "
        f"Growth={c['growth_score']:.0f} Master={c['master_score']:.1f}"
    )
    return "  - " + "\n  - ".join(parts)


def format_screen_report(result: Dict, top_n: int = 30) -> str:
    """Generate the full markdown report."""
    lines: List[str] = []
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    track_a = result.get('track_a', []) or []
    track_b = result.get('track_b', []) or []
    stats = result.get('stats', {}) or {}
    th = result.get('thresholds', {}) or {}

    # Header
    lines.append(f"# 📡 全市场CANSLIM扫描报告")
    lines.append("")
    lines.append(f"**扫描时间**: {ts}  ")
    lines.append(f"**耗时**: {result.get('elapsed_seconds', '-')}s  ")
    lines.append(f"**状态**: {result.get('status','-')}")
    if result.get('error'):
        lines.append(f"  ⚠️ `{result['error']}`")
    lines.append("")

    # Stats block
    lines.append("## 📊 扫描统计")
    lines.append("")
    lines.append(f"- 股票池规模: **{stats.get('universe_size', 0)}** 只")
    lines.append(f"- 预过滤后: **{stats.get('after_prefilter', 0)}** 只 (剔除ST/停牌/低流动性等)")
    lines.append(
        f"- 技术形态命中: A路线 **{stats.get('track_a_hits', 0)}** / "
        f"B路线 **{stats.get('track_b_hits', 0)}**"
    )
    lines.append(
        f"- 评分阈值通过 (A≥{th.get('track_a','?')} / B≥{th.get('track_b','?')}): "
        f"A路线 **{stats.get('final_a', 0)}** / B路线 **{stats.get('final_b', 0)}**"
    )
    lines.append(
        f"- K线拉取: {stats.get('kline_fetched', 0)} 次  财务拉取: {stats.get('fin_fetched', 0)} 次  "
        f"跳过: {result.get('skipped_count', 0)}"
    )

    # Skipped breakdown (collapsible details for diagnostic)
    skipped_summary = result.get('skipped_summary') or {}
    if skipped_summary:
        lines.append("")
        lines.append("<details><summary>📋 跳过原因明细</summary>")
        lines.append("")
        for reason, count in skipped_summary.items():
            lines.append(f"- {reason}: **{count}**")
        if result.get('skipped_path'):
            lines.append(f"- 完整列表见: `{result['skipped_path']}`")
        lines.append("")
        lines.append("</details>")
    lines.append("")

    # Track A
    lines.append("---")
    lines.append("")
    lines.append("## 🌱 A路线: 底部蓄势 (周线放量 + 基本面反转)")
    lines.append("")
    lines.append("> 关注周线连续放量、距52周低位较近，且基本面出现反转信号的标的。"
                 "适合左侧布局，需要耐心。")
    lines.append("")

    if not track_a:
        lines.append("_本次扫描无符合条件的候选。可调低 `track_a.weekly_vol_consecutive_weeks` "
                     "或 `track_a_threshold` 重试。_")
    else:
        lines.append("| 代码 | 名称 | 行业 | 现价 | 涨跌 | 连续放量 | 平均量比 | "
                     "跑52周低 | 跑52周高 | 反转过/利润/ROE/YoY/CF/GM | CANSLIM/Master | 评级 |")
        lines.append("|------|------|------|------|------|---------|----------|"
                     "----------|----------|----------------------|----------------|------|")
        for c in track_a[:top_n]:
            lines.append(_track_a_table_row(c))
        lines.append("")
        lines.append("### A路线 Top 5 入选理由")
        lines.append("")
        for i, c in enumerate(track_a[:5], 1):
            lines.append(f"**{i}. {c['name']} ({c['code']})** — {c.get('industry','')}  "
                         f"现价 ¥{c['price']:.2f}")
            lines.append(_why_a(c))
            lines.append("")

    # Track B
    lines.append("---")
    lines.append("")
    lines.append("## 🚀 B路线: 强势创新高 (RS≥60 + 距MA60 +10~+60% + 均线多头)")
    lines.append("")
    lines.append("> 关注临近或突破52周新高、距 MA60 健康偏离、量能持续上行的标的。"
                 "右侧追踪型，距 MA60 距离是最强分级指标。")
    lines.append("")

    if not track_b:
        lines.append("_本次扫描无符合条件的候选。可调宽 `track_b.max_pct_from_52w_high` "
                     "或调低 `min_relative_strength` / `min_pct_above_ma60` 重试。_")
    else:
        lines.append("| 代码 | 名称 | 行业 | 现价 | 涨跌 | 距52周高 | RS | 距MA60 | 量比 | "
                     "周线MA20稳 | CANSLIM/Master | 评级 |")
        lines.append("|------|------|------|------|------|----------|------|--------|------|"
                     "------------|----------------|------|")
        for c in track_b[:top_n]:
            lines.append(_track_b_table_row(c))
        lines.append("")
        lines.append("### B路线 Top 5 入选理由")
        lines.append("")
        for i, c in enumerate(track_b[:5], 1):
            lines.append(f"**{i}. {c['name']} ({c['code']})** — {c.get('industry','')}  "
                         f"现价 ¥{c['price']:.2f}")
            lines.append(_why_b(c))
            lines.append("")

    # Track C — observation pool (no fundamentals, just technical radar)
    track_c = result.get('track_c') or []
    track_c_plus = [c for c in track_c if c.get('is_c_plus')]
    track_c_base = [c for c in track_c if not c.get('is_c_plus')]

    lines.append("---")
    lines.append("")
    lines.append("## 🌅 C路线: 起涨前雷达 (观察池, 非买入信号)")
    lines.append("")
    lines.append("> 起涨前 1-4 周特征 (实证基于 42 只 YTD≥50% 牛股回测): "
                 "前 10 天温和上涨 + 量能 1.0-2.0x + 已站上 MA60 + 距 60 日低 5-50%. "
                 "**召回率 50%, 精度 8%** — 用于建立观察池，需配合主题/板块/基本面二次过滤。")
    lines.append("")

    if not track_c:
        lines.append("_本次扫描无符合条件的候选。_")
    else:
        stats = result.get('stats') or {}
        total_c = int(stats.get('final_c', len(track_c)) or len(track_c))
        total_c_plus = int(stats.get('final_c_plus', len(track_c_plus)) or len(track_c_plus))
        # If display was capped, note both the total discovered and what's shown
        if total_c > len(track_c) or total_c_plus > len(track_c_plus):
            lines.append(
                f"_共发现 **{total_c}** 只 C 候选, 其中 **{total_c_plus}** 只为 C+（基本面同步改善）_  \n"
                f"_报告展示: C+ **{len(track_c_plus)}** / C 基础 **{len(track_c_base)}** "
                f"(按 top_c_plus / top_c_base 配置截断)_"
            )
        else:
            lines.append(f"_共发现 **{total_c}** 只 C 候选, 其中 **{total_c_plus}** 只为 C+（基本面同步改善）_")
        lines.append("")

        # ---- C+ subset (high quality) ----
        if track_c_plus:
            lines.append("### ⭐ C+ 高质量子集 (技术起涨 + 基本面已改善)")
            lines.append("")
            lines.append("> 这些股不仅满足 C 路线技术条件，还在年报中显示基本面正向信号 "
                         "(利润转正 / ROE改善 / 营收未崩塌 / 毛利率改善 任 ≥2 项, 且 ROE ≥10%). "
                         "**优先观察**。")
            lines.append("")
            lines.append("| 代码 | 名称 | 现价 | 涨跌 | 前10d回 | 前10d量 | 距60d低 | "
                         "ROE | GM | NPGr | 信号(利/ROE/营/GM) |")
            lines.append("|------|------|------|------|---------|---------|---------|"
                         "------|------|------|--------------------|")
            for c in track_c_plus:
                ev = c.get('evidence') or {}
                fm = c.get('fund_metrics') or {}
                fs = c.get('fund_signals') or {}
                sig_str = '/'.join(['✅' if fs.get(k) else '➖' for k in
                                    ['profit_turn', 'roe_improving', 'revenue_floor', 'gm_improving']])
                lines.append(
                    f"| {c['code']} | {c.get('name','-')} | ¥{c.get('price',0):.2f} | "
                    f"{c.get('change_pct',0):+.2f}% | "
                    f"{ev.get('pre_return_pct','-')}% | "
                    f"{ev.get('pre_vol_ratio','-')}x | "
                    f"+{ev.get('pct_from_60d_low','-')}% | "
                    f"{fm.get('roe','-')}% | {fm.get('gm','-')}% | {fm.get('np_growth','-')}% | "
                    f"{sig_str} |"
                )
            lines.append("")

        # ---- C base (technical only) ----
        if track_c_base:
            lines.append(f"### C 基础观察池 ({len(track_c_base)} 只, 仅技术信号)")
            lines.append("")
            lines.append("| 代码 | 名称 | 现价 | 涨跌 | 前10d回 | 前10d量 | 距60d低 | 距52w高 | ROE | NPGr |")
            lines.append("|------|------|------|------|---------|---------|---------|---------|------|------|")
            for c in track_c_base[:50]:
                ev = c.get('evidence') or {}
                fm = c.get('fund_metrics') or {}
                lines.append(
                    f"| {c['code']} | {c.get('name','-')} | ¥{c.get('price',0):.2f} | "
                    f"{c.get('change_pct',0):+.2f}% | "
                    f"{ev.get('pre_return_pct','-')}% | "
                    f"{ev.get('pre_vol_ratio','-')}x | "
                    f"+{ev.get('pct_from_60d_low','-')}% | "
                    f"-{ev.get('pct_from_52w_high','-')}% | "
                    f"{fm.get('roe','-')}% | {fm.get('np_growth','-')}% |"
                )
            lines.append("")

    # Footer
    lines.append("---")
    lines.append("")
    lines.append("> ⚠️ **风险提示**: 本扫描仅基于公开市场技术与财务数据，"
                 "不构成投资建议。任何买入决策需结合自身风险承受能力、"
                 "完整研究与仓位管理规则。")
    lines.append("")
    lines.append(f"_由 china-stock skill 生成 / {datetime.now():%Y-%m-%d %H:%M}_")
    return "\n".join(lines)


def format_wechat_summary(result: Dict, top_n: int = 10) -> str:
    """Compact WeChat summary message."""
    lines: List[str] = []
    track_a = (result.get('track_a') or [])[:top_n]
    track_b = (result.get('track_b') or [])[:top_n]
    stats = result.get('stats', {}) or {}

    lines.append(f"📡 **CANSLIM 扫描器**")
    lines.append(f"_{datetime.now():%Y-%m-%d %H:%M} · 耗时 {result.get('elapsed_seconds','-')}s_")
    lines.append("")
    lines.append(
        f"池: {stats.get('universe_size',0)} → 预过滤 {stats.get('after_prefilter',0)} → "
        f"A {stats.get('final_a',0)} / B {stats.get('final_b',0)} / "
        f"C观察池 {stats.get('final_c',0)} (含 C+ {stats.get('final_c_plus', 0)})"
    )
    lines.append("")

    if track_a:
        lines.append(f"🌱 **A路线 (底部蓄势 Top {len(track_a)})**")
        for c in track_a:
            ev = c.get('evidence') or {}
            lines.append(
                f"• `{c['code']}` {c['name']} ¥{c['price']:.2f} "
                f"({c['change_pct']:+.1f}%) "
                f"M{c['master_score']:.0f} 连放{ev.get('consec_high_vol_weeks','-')}周 "
                f"距低{ev.get('pct_from_low','-')}%"
            )
    else:
        lines.append("🌱 A路线: 无候选")

    lines.append("")
    if track_b:
        lines.append(f"🚀 **B路线 (强势新高 Top {len(track_b)})**")
        for c in track_b:
            ev = c.get('evidence') or {}
            lines.append(
                f"• `{c['code']}` {c['name']} ¥{c['price']:.2f} "
                f"({c['change_pct']:+.1f}%) "
                f"M{c['master_score']:.0f} RS={ev.get('relative_strength','-')} "
                f"量{ev.get('vol_5d_vs_20d','-')}x"
            )
    else:
        lines.append("🚀 B路线: 无候选")

    lines.append("")
    lines.append("_仅供参考, 非投资建议_")
    return "\n".join(lines)
