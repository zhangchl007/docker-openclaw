#!/usr/bin/env python3
"""
Market Screener - Two-track CANSLIM candidate scanner

Track A — 底部蓄势放量 + 基本面反转
  Weekly: stock near 52-week low, moderate-volume accumulation for 3-4 consecutive weeks,
          combined with a profit-growth turn-positive / ROE-improvement signal.

Track B — 强势创新高 + 量能突破
  Daily/Weekly: stock within ~5% of 52-week high, MA bullish stack, RS >= 80,
          5-day volume vs 20-day MA volume >= 1.5.

Universe: CSI 800 (000906) + ChiNext composite (399102) by default.
Manual trigger: `python runner.py screen`.

All thresholds live in trading-rules.json -> "screener".
"""

import json
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

# Local imports (skill directory is on sys.path via runner.py)
from stock_data import (
    get_provider,
    StockQuote,
    StockFinancials,
    StockDataProvider,
)
from analyzers import (
    MasterAnalyzer,
    AnalysisResult,
    to_weekly,
    detect_weekly_volume_accumulation,
    detect_new_high_breakout,
    detect_pre_ignition,
    check_fundamental_reversal,
    derive_single_quarter,
)


CACHE_DIR = Path('/home/node/.openclaw/stock-data/cache')
LOG_DIR = Path('/home/node/.openclaw/stock-data/logs')


# ============================================================
# Data classes
# ============================================================


@dataclass
class Candidate:
    """A single screener hit."""
    code: str
    name: str
    track: str  # "A" or "B"
    industry: str = ""
    price: float = 0.0
    change_pct: float = 0.0
    pe: float = 0.0
    pb: float = 0.0
    market_cap_yi: float = 0.0
    avg_amount_yi_5d: float = 0.0
    # Pattern evidence
    evidence: Dict = field(default_factory=dict)
    # Fundamental reversal evidence (track A only)
    fund_reversal: Dict = field(default_factory=dict)
    fund_reversal_passed: bool = False        # whether soft gate was satisfied
    # CANSLIM master scoring
    master_score: float = 0.0                  # final score after adjustments
    master_score_raw: float = 0.0              # original (pre-adjustment) score
    master_rating: str = ""
    master_emoji: str = ""
    canslim_score: float = 0.0
    value_score: float = 0.0
    growth_score: float = 0.0
    # Score adjustments (transparency)
    score_adjustments: Dict = field(default_factory=dict)


# ============================================================
# Universe builder
# ============================================================


class UniverseBuilder:
    """Build the scanning universe from configured indices."""

    def __init__(self, provider: StockDataProvider, cfg: Dict, log_fn=print):
        self.provider = provider
        self.cfg = cfg
        self.log = log_fn

    def build(self) -> List[Tuple[str, str]]:
        """Return list of (code, name) for the union of configured indices.

        Cached to disk for `universe_cache_hours` (default 24h).
        """
        ttl_min = int(self.cfg.get('universe_cache_hours', 24)) * 60
        indices = self.cfg.get('indices', ['000906', '399102'])
        cache_key = f"screener_universe_{'_'.join(sorted(indices))}"

        cached = self.provider.cache.get(cache_key, ttl_min=ttl_min)
        if cached:
            self.log(f"[Universe] cache hit: {len(cached)} stocks")
            return [(c['code'], c.get('name', '')) for c in cached]

        try:
            import akshare as ak
        except ImportError:
            self.log("[Universe] akshare not installed, falling back to watchlist")
            return self._fallback_to_watchlist()

        members: Dict[str, str] = {}
        for idx in indices:
            self.log(f"[Universe] fetching index {idx}...")
            try:
                df = ak.index_stock_cons(symbol=idx)
                # akshare 返回列名不固定，尝试常见的
                code_col = None
                name_col = None
                for c in df.columns:
                    cl = str(c).lower()
                    if code_col is None and ('code' in cl or '代码' in str(c)):
                        code_col = c
                    if name_col is None and ('name' in cl or '名称' in str(c)):
                        name_col = c
                if code_col is None:
                    self.log(f"[Universe] {idx}: cannot locate code column in {df.columns.tolist()}")
                    continue
                for _, row in df.iterrows():
                    raw = str(row[code_col]).strip()
                    code = ''.join(ch for ch in raw if ch.isdigit())
                    if not code or len(code) != 6:
                        continue
                    name = str(row[name_col]).strip() if name_col else ""
                    members[code] = name
                self.log(f"[Universe] {idx}: {len(df)} members")
            except Exception as e:
                self.log(f"[Universe] {idx} failed: {e}")

        if not members:
            self.log("[Universe] all indices failed, falling back to watchlist")
            return self._fallback_to_watchlist()

        # Persist
        records = [{'code': c, 'name': n} for c, n in members.items()]
        self.provider.cache.set(cache_key, records)
        self.log(f"[Universe] built: {len(records)} stocks (cached)")
        return [(c, n) for c, n in members.items()]

    def _fallback_to_watchlist(self) -> List[Tuple[str, str]]:
        """Last-resort: use watchlist + peer_compare expansion."""
        wl_path = Path('/home/node/.openclaw/stock-data/watchlist.json')
        if not wl_path.exists():
            return []
        try:
            wl = json.load(open(wl_path))
            seen: Dict[str, str] = {}
            sectors = wl.get('sectors', {}) or wl.get('groups', {})
            for _, sec in sectors.items():
                stocks = sec.get('stocks') if isinstance(sec, dict) else sec
                if not stocks:
                    continue
                for s in stocks:
                    code = str(s.get('code', '')).strip()
                    if code and not code.startswith('hk'):
                        seen[code] = s.get('name', '')
                    for p in (s.get('peer_compare') or []):
                        p = str(p).strip()
                        if p and not p.startswith('hk'):
                            seen.setdefault(p, '')
            return list(seen.items())
        except Exception as e:
            self.log(f"[Universe] watchlist fallback failed: {e}")
            return []


# ============================================================
# Industry resolver (caches a minimal stock_meta per code)
# ============================================================


class IndustryResolver:
    """Best-effort fetch of industry name from akshare, cached 7 days."""

    def __init__(self, provider: StockDataProvider, log_fn=print):
        self.provider = provider
        self.log = log_fn

    def get_meta(self, code: str) -> Dict:
        cache_key = f"stock_industry_{code}"
        cached = self.provider.cache.get(cache_key, ttl_min=10080)
        if cached:
            return cached

        meta = {'industry': '', 'sub_industry': '', 'lynch_category': 'unknown'}
        try:
            import akshare as ak
            df = ak.stock_individual_info_em(symbol=code)
            for _, row in df.iterrows():
                k = str(row.get('item', ''))
                v = str(row.get('value', ''))
                if k in ('行业', '所属行业'):
                    meta['industry'] = v
                    meta['sub_industry'] = v
                    break
        except Exception:
            pass

        # cache even if empty (avoid retry storms)
        self.provider.cache.set(cache_key, meta)
        return meta


# ============================================================
# MarketScreener
# ============================================================


class MarketScreener:
    """Two-track CANSLIM screener."""

    def __init__(self,
                 rules: Dict,
                 universe_override: Optional[List[Tuple[str, str]]] = None,
                 log_fn=None):
        self.provider = get_provider()
        self.analyzer = MasterAnalyzer()
        self.rules = rules or {}
        self.universe_override = universe_override
        self._log = log_fn or self._default_log

        u_cfg = self.rules.get('universe', {})
        self.universe_builder = UniverseBuilder(self.provider, u_cfg, self._log)
        self.industry_resolver = IndustryResolver(self.provider, self._log)

        ex = self.rules.get('execution', {})
        self.max_workers_quotes = int(ex.get('max_workers_quotes', 4))
        self.max_workers_kline = int(ex.get('max_workers_kline', 8))
        self.request_sleep = float(ex.get('request_sleep_ms', 300)) / 1000
        self.kline_days = int(ex.get('kline_days', 260))
        self.fin_history_years = int(ex.get('financial_history_years', 3))
        # K线数据源: 'akshare' (并行, 推荐) | 'baostock' (串行) | 'auto' (akshare→baostock)
        self.kline_source = str(ex.get('kline_source', 'akshare')).lower()

        self.skipped: Dict[str, str] = {}
        self.stats = {
            'universe_size': 0,
            'after_prefilter': 0,
            'track_a_hits': 0,
            'track_b_hits': 0,
            'track_c_hits': 0,
            'final_a': 0,
            'final_b': 0,
            'final_c': 0,
            'final_c_plus': 0,
            'kline_fetched': 0,
            'fin_fetched': 0,
        }

    def _default_log(self, msg: str):
        print(f"[Screener] {msg}", flush=True)

    # ----------------------------------------------------
    # Stage 1: Universe + cheap prefilter (quotes only)
    # ----------------------------------------------------

    def build_universe(self) -> List[Tuple[str, str]]:
        if self.universe_override is not None:
            self._log(f"[Universe] override: {len(self.universe_override)} stocks")
            return list(self.universe_override)
        return self.universe_builder.build()

    def prefilter(self, codes_names: List[Tuple[str, str]]) -> Dict[str, Dict]:
        """Fetch quotes in batches, drop ST / suspended / illiquid / micro-caps.

        Returns: {code: {'name', 'quote': StockQuote}} for survivors.
        """
        u_cfg = self.rules.get('universe', {})
        exclude_st = bool(u_cfg.get('exclude_st', True))
        min_mcap = float(u_cfg.get('min_market_cap_yi', 50))
        # min_avg_amount handled later using K-line

        # Build code->name map
        name_map = {c: n for c, n in codes_names}
        codes = [c for c, _ in codes_names]
        self.stats['universe_size'] = len(codes)

        # Batch quotes (Tencent batch endpoint already supports many at once,
        # but be conservative — chunk into groups of 200)
        quotes: Dict[str, StockQuote] = {}
        BATCH = 200
        batches = [codes[i:i + BATCH] for i in range(0, len(codes), BATCH)]
        self._log(f"[Prefilter] fetching quotes in {len(batches)} batches of <={BATCH}")

        for i, batch in enumerate(batches):
            try:
                q = self.provider.get_quotes(batch)
                quotes.update(q)
                self._log(f"[Prefilter] batch {i+1}/{len(batches)}: {len(q)}/{len(batch)} quotes")
            except Exception as e:
                self._log(f"[Prefilter] batch {i+1} failed: {e}")
            time.sleep(self.request_sleep)

        # Apply cheap filters
        survivors: Dict[str, Dict] = {}
        for code, q in quotes.items():
            name = q.name or name_map.get(code, '')
            if not name:
                self.skipped[code] = 'no_name'
                continue
            if exclude_st and ('ST' in name.upper() or '退' in name):
                self.skipped[code] = 'st_or_delist'
                continue
            if q.price <= 0:
                self.skipped[code] = 'no_price_or_suspended'
                continue
            # Market cap proxy via PE/PB is unreliable; we skip cap filter unless
            # quote provides it. Tencent's quote does NOT include market cap directly.
            # We'll treat amount * 100 (avg trades day approx) below in K-line stage.
            survivors[code] = {'name': name, 'quote': q}

        self.stats['after_prefilter'] = len(survivors)
        self._log(f"[Prefilter] {len(survivors)}/{len(codes)} survived (skipped {len(self.skipped)})")
        return survivors

    # ----------------------------------------------------
    # Stage 2: Per-stock technical scan
    #   - K-line fetch is SERIAL (Baostock shares one login, not thread-safe)
    #   - Detector logic runs as we iterate (cheap, in-memory)
    # ----------------------------------------------------

    def _scan_one(self, code: str, info: Dict, df: pd.DataFrame) -> Optional[Tuple[str, Dict]]:
        """Run track A + track B detectors on already-fetched K-line.

        Returns (track, evidence_dict) or None if neither matches.
        Track precedence: B (new-high) > A (bottom). A stock can't be in both.
        """
        if df is None or df.empty or len(df) < 60:
            self.skipped[code] = 'insufficient_kline'
            return None

        # Liquidity filter via K-line amount (avg over last 5 trading days)
        u_cfg = self.rules.get('universe', {})
        min_amt_yi = float(u_cfg.get('min_avg_amount_yi_5d', 1.0))
        if 'amount' in df.columns:
            try:
                avg_amt = float(df['amount'].tail(5).mean())
                avg_amt_yi = avg_amt / 1e8  # baostock amount unit: yuan
                if avg_amt_yi < min_amt_yi:
                    self.skipped[code] = f'illiquid_{avg_amt_yi:.2f}yi'
                    return None
                info['avg_amount_yi_5d'] = round(avg_amt_yi, 2)
            except Exception:
                pass

        weekly = to_weekly(df)

        # Track B first (new-high momentum) — typically rarer
        b_cfg = self.rules.get('track_b_new_high_momentum', {})
        if b_cfg.get('enabled', True):
            ok, ev = detect_new_high_breakout(
                daily_df=df,
                weekly_df=weekly,
                max_pct_from_high=float(b_cfg.get('max_pct_from_high', 10)),
                min_relative_strength=float(b_cfg.get('min_relative_strength', 60)),
                vol_breakout_ratio_min=float(b_cfg.get('vol_breakout_ratio_min', 0.9)),
                weekly_vol_ratio_min=float(b_cfg.get('weekly_vol_ratio_min', 1.0)),
                ma_alignment_required=bool(b_cfg.get('ma_alignment_required', True)),
                max_distance_from_ma20_pct=float(b_cfg.get('max_distance_from_ma20_pct', 25)),
                min_pct_above_ma60=float(b_cfg.get('min_pct_above_ma60', 10)),
                max_pct_above_ma60=float(b_cfg.get('max_pct_above_ma60', 60)),
                min_weeks_above_ma20=int(b_cfg.get('min_weeks_above_ma20', 4)),
            )
            if ok:
                return ('B', ev)

        # Track A (bottom accumulation)
        a_cfg = self.rules.get('track_a_bottom_accumulation', {})
        if a_cfg.get('enabled', True):
            up_cfg = a_cfg.get('recent_uptrend', {}) or {}
            ok, ev = detect_weekly_volume_accumulation(
                weekly_df=weekly,
                lookback_weeks=int(a_cfg.get('min_weeks_lookback', 8)),
                vol_ratio_min=float(a_cfg.get('weekly_vol_vs_ma_min', 1.10)),
                consecutive_weeks=int(a_cfg.get('weekly_vol_consecutive_weeks', 3)),
                max_pct_from_low=float(a_cfg.get('max_pct_from_52w_low', 35)),
                min_pct_from_high=float(a_cfg.get('min_pct_from_52w_high', 25)),
                max_volatility_pct=float(a_cfg.get('weekly_volatility_max_pct', 12)),
                uptrend_weeks=int(up_cfg.get('weeks_window', 3)) if up_cfg.get('enabled', True) else 0,
                uptrend_min_pct=float(up_cfg.get('min_pct_up', 3)),
            )
            if ok:
                return ('A', ev)

        # Track C (pre-ignition radar) — lowest precision, broadest recall
        c_cfg = self.rules.get('track_c_pre_ignition', {})
        if c_cfg.get('enabled', True):
            ok, ev = detect_pre_ignition(
                daily_df=df,
                weekly_df=weekly,
                pre_window_days=int(c_cfg.get('pre_window_days', 10)),
                baseline_window_days=int(c_cfg.get('baseline_window_days', 20)),
                pre_return_min_pct=float(c_cfg.get('pre_return_min_pct', -5)),
                pre_return_max_pct=float(c_cfg.get('pre_return_max_pct', 15)),
                pre_vol_ratio_min=float(c_cfg.get('pre_vol_ratio_min', 1.0)),
                pre_vol_ratio_max=float(c_cfg.get('pre_vol_ratio_max', 2.0)),
                require_above_ma20=bool(c_cfg.get('require_above_ma20', True)),
                require_above_ma60=bool(c_cfg.get('require_above_ma60', True)),
                min_pct_from_60d_low=float(c_cfg.get('min_pct_from_60d_low', 5)),
                max_pct_from_60d_low=float(c_cfg.get('max_pct_from_60d_low', 50)),
            )
            if ok:
                return ('C', ev)

        return None

    def _fetch_kline(self, code: str) -> Optional[pd.DataFrame]:
        """Fetch K-line via configured source (akshare/baostock/auto)."""
        try:
            df = self.provider.get_history(
                code, days=self.kline_days, source=self.kline_source
            )
            return df
        except Exception as e:
            self.skipped[code] = f'kline_error: {e}'
            return None

    def technical_scan(self, survivors: Dict[str, Dict]) -> Dict[str, Dict]:
        """K-line fetch + per-stock detection.

        Parallel when source supports it (akshare/auto, HTTP), serial for Baostock
        (shared login, not thread-safe).

        Each stock has a hard timeout (per_stock_timeout_sec). If a single stock
        gets stuck (slow API, malformed data, runaway computation), it is skipped
        rather than blocking the whole scan.

        Returns {code: {'track', 'evidence', ...info}}.
        """
        hits: Dict[str, Dict] = {}
        items = list(survivors.items())

        parallel = self.kline_source in ('akshare', 'auto')
        workers = self.max_workers_kline if parallel else 1
        ex_cfg = self.rules.get('execution', {})
        per_stock_timeout = float(ex_cfg.get('per_stock_timeout_sec', 15))
        progress_step = int(ex_cfg.get('progress_log_every', 25))
        mode = f"parallel x{workers} via {self.kline_source}" if parallel else "serial Baostock"
        self._log(
            f"[TechScan] scanning {len(items)} stocks "
            f"({mode}, timeout={per_stock_timeout}s/stock, log/{progress_step})..."
        )

        t0 = time.time()
        done = [0]
        import threading
        lock = threading.Lock()

        def _scan_inner(code: str, info: Dict):
            """Runs in a worker thread; can be cancelled via timeout."""
            df = self._fetch_kline(code)
            if df is not None:
                self.stats['kline_fetched'] += 1
            try:
                return self._scan_one(code, info, df) if df is not None else None
            except Exception as e:
                self.skipped[code] = f'scan_error: {e}'
                return None

        def _record(code: str, info: Dict, res):
            if res:
                track, ev = res
                with lock:
                    hits[code] = {
                        'name': info['name'],
                        'quote': info['quote'],
                        'avg_amount_yi_5d': info.get('avg_amount_yi_5d', 0.0),
                        'track': track,
                        'evidence': ev,
                    }
            with lock:
                done[0] += 1
                d = done[0]
            if d % progress_step == 0 or d == len(items):
                self._log(
                    f"[TechScan] progress {d}/{len(items)} hits={len(hits)} "
                    f"elapsed={time.time()-t0:.1f}s"
                )

        if parallel:
            # Parallel mode: each stock in its own worker, with timeout.
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futs = {pool.submit(_scan_inner, code, info): (code, info) for code, info in items}
                for fut in as_completed(futs):
                    code, info = futs[fut]
                    try:
                        res = fut.result(timeout=per_stock_timeout)
                    except Exception as e:
                        self.skipped[code] = f'timeout_or_error: {e}'
                        res = None
                    _record(code, info, res)
        else:
            # Serial mode (Baostock): wrap each stock in a single-thread executor
            # so we can enforce a hard timeout even though the API itself is serial.
            with ThreadPoolExecutor(max_workers=1) as pool:
                for code, info in items:
                    fut = pool.submit(_scan_inner, code, info)
                    try:
                        res = fut.result(timeout=per_stock_timeout)
                    except Exception as e:
                        self.skipped[code] = f'timeout_or_error: {type(e).__name__}'
                        res = None
                        # Cancel the future so the next iteration starts clean
                        fut.cancel()
                    _record(code, info, res)
                    if self.request_sleep > 0:
                        time.sleep(self.request_sleep)

        a_count = sum(1 for h in hits.values() if h['track'] == 'A')
        b_count = sum(1 for h in hits.values() if h['track'] == 'B')
        c_count = sum(1 for h in hits.values() if h['track'] == 'C')
        self.stats['track_a_hits'] = a_count
        self.stats['track_b_hits'] = b_count
        self.stats['track_c_hits'] = c_count
        skipped_in_scan = sum(1 for v in self.skipped.values() if 'timeout' in v or 'error' in v)
        self._log(
            f"[TechScan] hits: track A={a_count}, track B={b_count}, track C={c_count}, "
            f"timed-out/errored={skipped_in_scan}, total elapsed={time.time()-t0:.1f}s"
        )
        return hits

    # ----------------------------------------------------
    # Stage 3: Fundamentals + scoring (sequential, expensive)
    # ----------------------------------------------------

    def _enrich_one(self, code: str, hit: Dict) -> Optional[Candidate]:
        track = hit['track']
        q: StockQuote = hit['quote']
        name = hit['name']
        try:
            f = self.provider.get_financials(code)
            self.stats['fin_fetched'] += 1
        except Exception as e:
            self.skipped[code] = f'fin_error: {e}'
            return None

        history = []
        try:
            history = self.provider.get_financial_history(code, years=self.fin_history_years)
        except Exception:
            history = []

        # Quarterly data (A股 only) for QoQ + cash-flow signals
        quarterly = []
        if not str(code).startswith('hk'):
            try:
                raw_q = self.provider.get_quarterly_data(code, n_quarters=8)
                quarterly = derive_single_quarter(raw_q)
            except Exception:
                quarterly = []

        # Track A: fundamental reversal as gate.
        # Stocks failing reversal can still pass via "volume_override" if they
        # exhibit truly extreme accumulation (fat-tail volume burst).
        fund_ev: Dict = {}
        fund_ok = False
        volume_override_used = False
        if track == 'A':
            a_cfg = self.rules.get('track_a_bottom_accumulation', {})
            fr_cfg = a_cfg.get('fundamental_reversal', {})
            fund_ok, fund_ev = check_fundamental_reversal(
                f,
                history=history,
                quarterly=quarterly,
                profit_growth_turn_positive=bool(fr_cfg.get('profit_growth_turn_positive', True)),
                roe_yoy_improvement_min=float(fr_cfg.get('roe_yoy_improvement_min_pct', 0)),
                revenue_growth_min=float(fr_cfg.get('revenue_growth_min_pct', -10)),
                check_qoq_improvement=bool(fr_cfg.get('check_qoq_improvement', True)),
                check_cashflow_positive=bool(fr_cfg.get('check_cashflow_positive', True)),
                check_gross_margin_improvement=bool(fr_cfg.get('check_gross_margin_improvement', True)),
                gross_margin_min_improvement_pct=float(fr_cfg.get('gross_margin_min_improvement_pct', 1.0)),
                require_all=bool(fr_cfg.get('require_all', False)),
            )

            mode = str(fr_cfg.get('mode', 'hard')).lower()
            if mode == 'hard' and not fund_ok:
                # Try volume_override: only when accumulation is so extreme that
                # market is clearly leading fundamentals.
                vo_cfg = a_cfg.get('volume_override', {}) or {}
                if vo_cfg.get('enabled', False):
                    ev = hit.get('evidence') or {}
                    consec = int(ev.get('consec_high_vol_weeks', 0) or 0)
                    avg_r = float(ev.get('avg_vol_ratio', 0) or 0)
                    peak_r = float(ev.get('peak_vol_ratio', 0) or 0)
                    min_w = int(vo_cfg.get('min_consecutive_weeks', 8))
                    min_avg = float(vo_cfg.get('min_avg_ratio', 2.0))
                    min_peak = float(vo_cfg.get('min_peak_ratio', 3.5))
                    if consec >= min_w and avg_r >= min_avg and peak_r >= min_peak:
                        volume_override_used = True
                        self._log(
                            f"[VolumeOverride] {code} {name} "
                            f"consec={consec}w avg={avg_r:.2f}x peak={peak_r:.2f}x "
                            f"→ bypass fund_reversal"
                        )

                if not volume_override_used:
                    sig_brief = (
                        f"profit_turn={int(bool(fund_ev.get('signal_profit_turn_positive')))}"
                        f"/roe_imp={int(bool(fund_ev.get('signal_roe_improving')))}"
                        f"/rev_floor={int(bool(fund_ev.get('signal_revenue_floor')))}"
                        f"/qoq={int(bool(fund_ev.get('signal_qoq_first_improvement')))}"
                        f"/cf={int(bool(fund_ev.get('signal_cashflow_turn_positive')))}"
                        f"/gm={int(bool(fund_ev.get('signal_gross_margin_improving')))}"
                    )
                    self.skipped[code] = f"fund_reversal_failed: {sig_brief}"
                    return None

        # CANSLIM/Value/Growth scoring
        try:
            df = self.provider.get_history(code, days=self.kline_days, source=self.kline_source)
            meta = self.industry_resolver.get_meta(code)
            scoring = self.analyzer.analyze(q, f, df, meta)
        except Exception as e:
            self.skipped[code] = f'scoring_error: {e}'
            return None

        cs = scoring['canslim'].get('score', 0) if isinstance(scoring['canslim'], dict) else scoring['canslim'].score
        vs = scoring['value'].get('score', 0) if isinstance(scoring['value'], dict) else scoring['value'].score
        gs = scoring['growth'].get('score', 0) if isinstance(scoring['growth'], dict) else scoring['growth'].score

        # ---- Score adjustments (track A only) ----
        master_raw = float(scoring.get('master_score', 0))
        master_adj = master_raw
        adjustments: Dict = {}

        if track == 'A':
            a_cfg = self.rules.get('track_a_bottom_accumulation', {})
            adj_cfg = a_cfg.get('adjustments', {})

            # 1) Volume-override penalty: stocks bypassed fund_reversal via extreme volume
            #    are riskier — apply a penalty so they need stronger overall scores.
            if volume_override_used:
                vo_penalty = float(adj_cfg.get('volume_override_penalty', -10))
                if vo_penalty:
                    adjustments['volume_override'] = vo_penalty
                    master_adj += vo_penalty

            # 2) Long-streak bonus: more consecutive accumulation weeks
            consec = int(hit.get('evidence', {}).get('consec_high_vol_weeks', 0) or 0)
            t1 = int(adj_cfg.get('streak_threshold_1', 6))
            t2 = int(adj_cfg.get('streak_threshold_2', 10))
            b1 = float(adj_cfg.get('streak_bonus_1', 5))
            b2 = float(adj_cfg.get('streak_bonus_2', 10))
            if consec >= t2:
                adjustments[f'long_streak_bonus(>={t2}w)'] = b2
                master_adj += b2
            elif consec >= t1:
                adjustments[f'streak_bonus(>={t1}w)'] = b1
                master_adj += b1

        master_adj = max(0.0, min(100.0, master_adj))

        return Candidate(
            code=code,
            name=name,
            track=track,
            industry=meta.get('industry', ''),
            price=float(q.price or 0),
            change_pct=float(q.change_pct or 0),
            pe=float(q.pe or 0),
            pb=float(q.pb or 0),
            avg_amount_yi_5d=float(hit.get('avg_amount_yi_5d', 0)),
            evidence=hit['evidence'],
            fund_reversal=fund_ev,
            fund_reversal_passed=bool(fund_ok),
            master_score=float(master_adj),
            master_score_raw=float(master_raw),
            master_rating=str(scoring.get('master_rating', '')),
            master_emoji=str(scoring.get('master_emoji', '')),
            canslim_score=float(cs),
            value_score=float(vs),
            growth_score=float(gs),
            score_adjustments=adjustments,
        )

    def enrich_and_score(self, hits: Dict[str, Dict]) -> List[Candidate]:
        """Serial enrichment (Baostock financials are not thread-safe).

        Only Track A and B hits go through full enrichment (financials + scoring).
        Track C hits are watchlist-only — they bypass this expensive stage.

        K-line is already cached from technical_scan stage. Each stock has a
        per-stock timeout to avoid one bad stock blocking the whole stage.
        """
        candidates: List[Candidate] = []
        # Filter to only A/B for full enrichment (C is watchlist-only)
        items = [(code, h) for code, h in hits.items() if h.get('track') in ('A', 'B')]
        if not items:
            return []

        ex_cfg = self.rules.get('execution', {})
        per_stock_timeout = float(ex_cfg.get('enrich_timeout_sec', 30))

        self._log(f"[Enrich] scoring {len(items)} A/B hits (serial, timeout={per_stock_timeout}s/stock)...")

        with ThreadPoolExecutor(max_workers=1) as pool:
            for i, (code, hit) in enumerate(items, 1):
                fut = pool.submit(self._enrich_one, code, hit)
                try:
                    c = fut.result(timeout=per_stock_timeout)
                except Exception as e:
                    self.skipped[code] = f'enrich_timeout_or_error: {type(e).__name__}'
                    c = None
                    fut.cancel()
                if c:
                    candidates.append(c)
                if i % 10 == 0 or i == len(items):
                    self._log(f"[Enrich] progress {i}/{len(items)} accepted={len(candidates)}")
        return candidates

    def _enrich_track_c_with_fundamentals(self, c_raw: List[Dict]) -> List[Dict]:
        """Apply A-style fundamental signals to Track C candidates.

        Light-weight enrichment using only annual financials (cached 24h+) —
        no quarterly data fetch (too slow for 100+ candidates).

        Adds 4 quick signals (利润转正/ROE改善/营收未崩塌/毛利率改善) and a
        derived 'is_c_plus' flag for the high-quality subset:
            ≥2 positive fundamental signals AND ROE ≥ 10%

        This bridges Track C (technical breakout) and Track A (fundamental
        reversal): C+ = "fundamentals already supporting the breakout".
        """
        if not c_raw:
            return []

        c_cfg = self.rules.get('track_c_pre_ignition', {}) or {}
        post_cfg = c_cfg.get('post_filter', {}) or {}
        if not post_cfg.get('enabled', True):
            return c_raw  # post-filter disabled, return as-is

        ex_cfg = self.rules.get('execution', {})
        per_stock_timeout = float(ex_cfg.get('c_enrich_timeout_sec', 5))

        roe_min = float(post_cfg.get('roe_min', 10))
        roe_yoy_min = float(post_cfg.get('roe_yoy_improvement_min_pct', 0))
        revenue_min = float(post_cfg.get('revenue_growth_min_pct', -20))
        gm_min = float(post_cfg.get('gross_margin_min_improvement_pct', 0.5))
        n_signals_for_plus = int(post_cfg.get('signals_required_for_c_plus', 2))

        self._log(f"[TrackC+] enriching {len(c_raw)} candidates (annual only, timeout={per_stock_timeout}s)...")
        t0 = time.time()
        enriched = []

        with ThreadPoolExecutor(max_workers=1) as pool:
            for i, raw in enumerate(c_raw, 1):
                code = raw['code']
                # Fetch financials (cached 24h) + history (cached 7d) — should be fast
                fut = pool.submit(self._fetch_c_fundamentals, code)
                try:
                    fund = fut.result(timeout=per_stock_timeout)
                except Exception:
                    fund = None
                    fut.cancel()

                if not fund:
                    raw['fund_signals'] = {}
                    raw['fund_signals_count'] = 0
                    raw['is_c_plus'] = False
                    enriched.append(raw)
                    continue

                f, hist = fund
                cur_pg = float(f.profit_growth or 0)
                cur_roe = float(f.roe or 0)
                cur_rg = float(f.revenue_growth or 0)
                cur_gm = float(f.gross_margin or 0)
                prev_roe = float(hist[1].get('roe', 0)) if len(hist) >= 2 else 0
                prev_pg = float(hist[1].get('profit_growth', 0)) if len(hist) >= 2 else 0
                prev_gm = float(hist[1].get('gross_margin', 0)) if len(hist) >= 2 else 0

                sig_profit = cur_pg >= 0 and prev_pg < 0
                sig_roe = (cur_roe - prev_roe) >= roe_yoy_min
                sig_rev = cur_rg >= revenue_min
                sig_gm = (cur_gm - prev_gm) >= gm_min if cur_gm > 0 else False

                signals = {
                    'profit_turn': sig_profit,
                    'roe_improving': sig_roe,
                    'revenue_floor': sig_rev,
                    'gm_improving': sig_gm,
                }
                n_pos = sum(signals.values())

                # C+ criteria: enough signals + healthy ROE
                is_c_plus = (n_pos >= n_signals_for_plus) and (cur_roe >= roe_min)

                raw['fund_signals'] = signals
                raw['fund_signals_count'] = n_pos
                raw['is_c_plus'] = is_c_plus
                raw['fund_metrics'] = {
                    'roe': round(cur_roe, 2),
                    'gm': round(cur_gm, 2),
                    'np_growth': round(cur_pg, 2),
                    'rev_growth': round(cur_rg, 2),
                    'roe_yoy': round(cur_roe - prev_roe, 2),
                    'gm_yoy': round(cur_gm - prev_gm, 2),
                }
                enriched.append(raw)

                if i % 25 == 0 or i == len(c_raw):
                    n_plus = sum(1 for x in enriched if x.get('is_c_plus'))
                    self._log(f"[TrackC+] progress {i}/{len(c_raw)} C+={n_plus} elapsed={time.time()-t0:.1f}s")

        n_plus = sum(1 for x in enriched if x.get('is_c_plus'))
        self._log(f"[TrackC+] done: {n_plus} C+ stocks (≥{n_signals_for_plus} signals + ROE≥{roe_min}%) "
                  f"out of {len(enriched)} C candidates")
        return enriched

    def _fetch_c_fundamentals(self, code: str):
        """Helper: fetch latest financials + history for Track C+ check.

        Returns (StockFinancials, history_list) or None on failure.
        Both are cached (24h / 7d), so most calls are near-instant.
        """
        try:
            f = self.provider.get_financials(code)
            hist = self.provider.get_financial_history(
                code, years=int(self.fin_history_years)
            )
            return f, hist
        except Exception:
            return None


    # ----------------------------------------------------
    # Pipeline
    # ----------------------------------------------------

    def run(self) -> Dict:
        t0 = time.time()
        self._log("=" * 60)
        self._log(f"MarketScreener start at {datetime.now():%Y-%m-%d %H:%M:%S}")
        self._log("=" * 60)

        try:
            # Stage 1
            universe = self.build_universe()
            if not universe:
                return self._empty_result(t0, error='empty_universe')

            survivors = self.prefilter(universe)
            if not survivors:
                return self._empty_result(t0, error='all_filtered_out')

            # Stage 2
            hits = self.technical_scan(survivors)

            scoring_cfg = self.rules.get('scoring', {})
            a_thresh = float(scoring_cfg.get('track_a_threshold', 60))
            b_thresh = float(scoring_cfg.get('track_b_threshold', 70))
            top_n = int(scoring_cfg.get('top_n', 30))
            thresholds = {'track_a': a_thresh, 'track_b': b_thresh, 'top_n': top_n}

            if not hits:
                # No technical hits is a valid empty result, not an error
                skipped_summary = self._summarize_skipped()
                return {
                    'status': 'empty',
                    'reason': 'no_technical_hits',
                    'timestamp': datetime.now().isoformat(),
                    'elapsed_seconds': round(time.time() - t0, 1),
                    'stats': dict(self.stats),
                    'thresholds': thresholds,
                    'track_a': [],
                    'track_b': [],
                    'track_c': [],
                    'skipped_count': len(self.skipped),
                    'skipped_summary': skipped_summary,
                }

            # Stage 3
            candidates = self.enrich_and_score(hits)

            # Log every enriched candidate's score so we can see who almost made it
            for c in candidates:
                pass_mark = '✅' if c.master_score >= a_thresh else '❌'
                fund_mark = '✅' if c.fund_reversal_passed else '⚠️'
                adj_str = (', '.join(f"{k}{v:+.0f}" for k, v in (c.score_adjustments or {}).items())
                           or 'none')
                self._log(
                    f"[Score] {pass_mark} {c.code} {c.name} track={c.track} "
                    f"raw={c.master_score_raw:.1f} adj={c.master_score:.1f} "
                    f"fund={fund_mark} adjustments=[{adj_str}]"
                )

            # Apply scoring thresholds
            track_a = [c for c in candidates if c.track == 'A' and c.master_score >= a_thresh]
            track_b = [c for c in candidates if c.track == 'B' and c.master_score >= b_thresh]
            track_a.sort(key=lambda c: c.master_score, reverse=True)
            track_b.sort(key=lambda c: c.master_score, reverse=True)

            # Track C — watchlist (technical-only). Enrich with A-style fundamentals
            # to identify "C+" subset (technical breakout + fundamentals improving)
            top_c = int(scoring_cfg.get('top_c', 50))
            track_c_raw = [
                {
                    'code': code,
                    'name': h.get('name', ''),
                    'price': float(getattr(h.get('quote'), 'price', 0) or 0),
                    'change_pct': float(getattr(h.get('quote'), 'change_pct', 0) or 0),
                    'pe': float(getattr(h.get('quote'), 'pe', 0) or 0),
                    'evidence': h.get('evidence', {}),
                }
                for code, h in hits.items() if h.get('track') == 'C'
            ]

            # Apply A-style fundamental post-filter to enrich Track C with quality signals
            track_c_hits = self._enrich_track_c_with_fundamentals(track_c_raw)

            # Sort: C+ (with fundamentals) first, then by signal count + vol ratio
            track_c_hits.sort(
                key=lambda x: (
                    not x.get('is_c_plus', False),  # C+ first
                    -int(x.get('fund_signals_count', 0) or 0),  # more signals first
                    -float(x['evidence'].get('pre_vol_ratio') or 0),
                    abs(float(x['evidence'].get('pre_return_pct') or 0) - 6.0),
                )
            )

            self.stats['final_a'] = len(track_a)
            self.stats['final_b'] = len(track_b)
            self.stats['final_c'] = len(track_c_hits)
            self.stats['final_c_plus'] = sum(1 for c in track_c_hits if c.get('is_c_plus'))

            elapsed = time.time() - t0
            self._log(
                f"[Done] universe={self.stats['universe_size']} "
                f"prefilter={self.stats['after_prefilter']} "
                f"techA={self.stats['track_a_hits']} techB={self.stats['track_b_hits']} "
                f"techC={self.stats['track_c_hits']} "
                f"finalA={len(track_a)} finalB={len(track_b)} finalC={len(track_c_hits)} "
                f"(C+={self.stats.get('final_c_plus', 0)}) "
                f"elapsed={elapsed:.1f}s"
            )

            # Dump skipped breakdown for offline analysis
            skipped_summary = self._summarize_skipped()
            skipped_path = None
            if self.skipped:
                ts = datetime.now().strftime('%Y%m%d-%H%M')
                skipped_path = self._dump_skipped(
                    Path(f'/home/node/.openclaw/stock-data/reports/skipped-{ts}.json')
                )
                if skipped_path:
                    self._log(f"[Skipped] {len(self.skipped)} codes dumped to {skipped_path}")
                    top3 = list(skipped_summary.items())[:3]
                    summary_str = ', '.join(f"{k}={v}" for k, v in top3)
                    self._log(f"[Skipped] top buckets: {summary_str}")

            return {
                'status': 'success',
                'timestamp': datetime.now().isoformat(),
                'elapsed_seconds': round(elapsed, 1),
                'stats': dict(self.stats),
                'thresholds': thresholds,
                'track_a': [asdict(c) for c in track_a[:top_n]],
                'track_b': [asdict(c) for c in track_b[:top_n]],
                'track_c': track_c_hits[:top_c],
                'skipped_count': len(self.skipped),
                'skipped_summary': skipped_summary,
                'skipped_path': str(skipped_path) if skipped_path else None,
            }

        except Exception as e:
            self._log(f"[FATAL] {e}\n{traceback.format_exc()}")
            return self._empty_result(t0, error=str(e))

    # ----------------------------------------------------
    # Skipped diagnostics
    # ----------------------------------------------------

    def _summarize_skipped(self) -> Dict[str, int]:
        """Bucket skipped reasons into categories for quick analysis."""
        from collections import Counter
        buckets = Counter()
        for reason in self.skipped.values():
            r = str(reason)
            if r.startswith('illiquid'):
                key = 'illiquid (流动性不足)'
            elif r.startswith('insufficient_kline'):
                key = 'insufficient_kline (K线数据不足)'
            elif r.startswith('kline_error'):
                key = 'kline_error (K线接口失败)'
            elif r.startswith('timeout_or_error') or 'TimeoutError' in r:
                key = 'timeout_or_error (单股超时/错误)'
            elif r.startswith('scan_error'):
                key = 'scan_error (扫描计算错误)'
            elif r.startswith('fund_reversal_failed'):
                key = 'fund_reversal_failed (基本面反转未通过)'
            elif r.startswith('fin_error'):
                key = 'fin_error (财务接口失败)'
            elif r.startswith('scoring_error'):
                key = 'scoring_error (评分错误)'
            elif r.startswith('enrich_timeout_or_error'):
                key = 'enrich_timeout (Enrich超时)'
            elif r.startswith('st_or_delist'):
                key = 'st_or_delist (ST/退市)'
            elif r.startswith('no_price_or_suspended'):
                key = 'no_price (停牌/无报价)'
            elif r.startswith('no_name'):
                key = 'no_name (无股票名)'
            else:
                key = r.split(':')[0][:40]
            buckets[key] += 1
        return dict(buckets.most_common())

    def _dump_skipped(self, path: Path) -> Optional[Path]:
        """Write skipped codes + reasons to JSON file for offline analysis."""
        if not self.skipped:
            return None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                'timestamp': datetime.now().isoformat(),
                'count': len(self.skipped),
                'summary': self._summarize_skipped(),
                'details': dict(self.skipped),
            }
            with open(path, 'w') as fp:
                json.dump(payload, fp, ensure_ascii=False, indent=2)
            return path
        except Exception as e:
            self._log(f"[Skipped] dump failed: {e}")
            return None

    def _empty_result(self, t0: float, error: str = '') -> Dict:
        return {
            'status': 'error' if error else 'empty',
            'timestamp': datetime.now().isoformat(),
            'elapsed_seconds': round(time.time() - t0, 1),
            'stats': dict(self.stats),
            'error': error,
            'track_a': [],
            'track_b': [],
            'track_c': [],
            'skipped_count': len(self.skipped),
        }


# ============================================================
# CLI helper (for local testing without runner.py)
# ============================================================


def load_screener_rules(rules_path: Path = None) -> Dict:
    """Load the 'screener' section of trading-rules.json."""
    if rules_path is None:
        rules_path = Path('/home/node/.openclaw/stock-data/trading-rules.json')
    if not rules_path.exists():
        # fallback for local dev: workspace path
        alt = Path(__file__).resolve().parents[3] / 'stock-data' / 'trading-rules.json'
        if alt.exists():
            rules_path = alt
    with open(rules_path) as f:
        rules = json.load(f)
    return rules.get('screener', {}) or {}


if __name__ == '__main__':
    rules = load_screener_rules()
    if not rules:
        print("ERROR: 'screener' section not found in trading-rules.json")
        sys.exit(1)

    override = None
    if len(sys.argv) > 1 and sys.argv[1] == '--dry-run':
        override = [('600519', '贵州茅台'), ('000858', '五粮液'), ('002594', '比亚迪')]
        print(f"Dry-run mode: scanning {len(override)} stocks")

    screener = MarketScreener(rules=rules, universe_override=override)
    result = screener.run()
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
