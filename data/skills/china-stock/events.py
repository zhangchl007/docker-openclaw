#!/usr/bin/env python3
"""
Stock Event Scanner - 个股事件分析

扫描watchlist股票的重要事件信号：
1. 高管/董监高增减持 (insider trading)
2. 十大股东变动 (institutional holding changes)
3. 限售解禁 (restricted share release)
4. 回购 (buyback)

这些事件信号作为交易系统的补充维度。

信号权重:
  高管增持 → 强看多 (+15)
  社保/外资增持 → 中看多 (+10)
  高管大额减持 → 警告 (-10)
  大额解禁临近 → 警告 (-5)
  回购进行中 → 看多 (+8)
"""

import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List
from dataclasses import dataclass, asdict

try:
    import akshare as ak
    AKSHARE_AVAILABLE = True
except ImportError:
    AKSHARE_AVAILABLE = False

from stock_data import get_provider, parse_watchlist


@dataclass
class StockEvent:
    code: str
    name: str
    event_type: str     # insider_buy / insider_sell / inst_change / unlock / buyback
    signal: str         # bullish / bearish / neutral
    importance: str     # high / medium / low
    score: int          # -15 to +15
    summary: str
    detail: str
    date: str


class EventScanner:
    """Scan for corporate events that affect stock analysis"""

    def __init__(self):
        self.provider = get_provider()
        self.watchlist_path = Path('/home/node/.openclaw/stock-data/watchlist.json')
        self._cache_path = Path('/home/node/.openclaw/stock-data/cache/events_cache.json')
        self._cache_ttl_hours = 12  # Cache events for 12 hours

    def _load_codes_names(self) -> Dict[str, str]:
        """Load code->name mapping from watchlist"""
        if self.watchlist_path.exists():
            with open(self.watchlist_path) as f:
                wl = json.load(f)
            result = {}
            for stocks in parse_watchlist(wl).values():
                for s in stocks:
                    result[s['code']] = s.get('name', s['code'])
            return result
        return {}

    def scan_insider_trades(self, codes_names: Dict[str, str]) -> List[StockEvent]:
        """Scan insider (高管/股东) buy/sell per stock — no full market pull"""
        events = []
        if not AKSHARE_AVAILABLE:
            return events

        one_year_ago = datetime.now() - timedelta(days=365)

        for code, name in codes_names.items():
            if code.startswith('hk'):
                continue
            try:
                df = ak.stock_shareholder_change_ths(symbol=code)
                if df.empty:
                    continue

                for _, row in df.iterrows():
                    # Parse date
                    announce_date = row.get('公告日期')
                    if hasattr(announce_date, 'year'):
                        if announce_date < one_year_ago.date():
                            continue
                        date_str = str(announce_date)
                    else:
                        continue

                    person = str(row.get('变动股东', ''))
                    change_str = str(row.get('变动数量', ''))
                    price_str = str(row.get('交易均价', ''))

                    # Parse change amount
                    is_buy = '增持' in change_str
                    is_sell = '减持' in change_str
                    if not is_buy and not is_sell:
                        continue

                    # Parse number (e.g., "减持44.49万" or "增持2000.00")
                    num_str = change_str.replace('增持', '').replace('减持', '').strip()
                    try:
                        if '万' in num_str:
                            shares = float(num_str.replace('万', '')) * 10000
                        else:
                            shares = float(num_str)
                    except:
                        shares = 0

                    # Parse price
                    try:
                        price = float(price_str) if price_str != '未披露' else 0
                    except:
                        price = 0

                    amount = shares * price if price > 0 else 0

                    if is_buy:
                        importance = 'high' if amount > 1_000_000 else 'medium' if amount > 100_000 else 'low'
                        events.append(StockEvent(
                            code=code, name=name,
                            event_type='insider_buy', signal='bullish',
                            importance=importance,
                            score=min(15, int(amount / 500_000) + 5) if amount > 0 else 5,
                            summary=f"{person}增持{int(shares)}股",
                            detail=f"均价¥{price:.2f} 金额¥{amount:,.0f}" if price > 0 else "价格未披露",
                            date=date_str
                        ))
                    elif is_sell:
                        importance = 'high' if amount > 5_000_000 else 'medium' if amount > 1_000_000 else 'low'
                        events.append(StockEvent(
                            code=code, name=name,
                            event_type='insider_sell', signal='bearish',
                            importance=importance,
                            score=max(-10, -int(amount / 1_000_000) - 2) if amount > 0 else -2,
                            summary=f"{person}减持{int(shares)}股",
                            detail=f"均价¥{price:.2f} 金额¥{amount:,.0f}" if price > 0 else "价格未披露",
                            date=date_str
                        ))

                time.sleep(0.3)
            except Exception as e:
                pass

        return events

    def scan_shareholder_changes(self, codes_names: Dict[str, str]) -> List[StockEvent]:
        """Scan top 10 shareholder changes"""
        events = []
        if not AKSHARE_AVAILABLE:
            return events

        for code, name in codes_names.items():
            if code.startswith('hk'):
                continue
            try:
                prefix = 'sh' if code.startswith('6') else 'sz'
                df = ak.stock_gdfx_free_top_10_em(symbol=f'{prefix}{code}', date='20241231')
                if df.empty:
                    continue

                for _, row in df.iterrows():
                    holder = str(row.get('股东名称', ''))
                    change = str(row.get('增减', ''))
                    nature = str(row.get('股东性质', ''))
                    pct = float(row.get('占总流通股本持股比例', 0) or 0)

                    if change == '不变' or not change or change == 'nan':
                        continue

                    try:
                        change_shares = int(change)
                    except:
                        continue

                    # Key institutional holders
                    is_important = any(kw in holder for kw in ['社保', '汇金', '保险', '养老'])
                    is_foreign = '香港中央' in holder or '北向' in holder or 'QFII' in holder

                    if change_shares > 0:
                        if is_important:
                            events.append(StockEvent(
                                code=code, name=name,
                                event_type='inst_increase',
                                signal='bullish',
                                importance='high',
                                score=10,
                                summary=f"国家队/社保增持: {holder[:20]}",
                                detail=f"增持{change_shares}股 占比{pct:.1f}%",
                                date='2024Q4'
                            ))
                        elif is_foreign:
                            events.append(StockEvent(
                                code=code, name=name,
                                event_type='foreign_increase',
                                signal='bullish',
                                importance='medium',
                                score=8,
                                summary=f"外资增持: {holder[:20]}",
                                detail=f"增持{change_shares}股 占比{pct:.1f}%",
                                date='2024Q4'
                            ))
                    elif change_shares < 0 and (is_important or is_foreign):
                        events.append(StockEvent(
                            code=code, name=name,
                            event_type='inst_decrease',
                            signal='bearish',
                            importance='medium',
                            score=-5,
                            summary=f"{'国家队' if is_important else '外资'}减持: {holder[:20]}",
                            detail=f"减持{abs(change_shares)}股 占比{pct:.1f}%",
                            date='2024Q4'
                        ))

                time.sleep(0.3)
            except Exception as e:
                pass  # Skip failures silently

        return events

    def scan_block_trades(self, codes_names: Dict[str, str]) -> List[StockEvent]:
        """Scan block trades (大宗交易) — only for watchlist stocks"""
        events = []
        if not AKSHARE_AVAILABLE:
            return events

        try:
            end = datetime.now().strftime('%Y%m%d')
            start = (datetime.now() - timedelta(days=90)).strftime('%Y%m%d')
            df = ak.stock_dzjy_mrmx(start_date=start, end_date=end)
            if df.empty:
                return events

            # Only filter our watchlist codes
            our_codes = set(c for c in codes_names.keys() if not c.startswith('hk'))
            df = df[df['证券代码'].isin(our_codes)]
            if df.empty:
                return events

            provider = get_provider()
            quotes = provider.get_quotes(list(our_codes))

            for code, name in codes_names.items():
                if code.startswith('hk'):
                    continue

                stock_trades = df[df['证券代码'] == code]
                if stock_trades.empty:
                    continue

                q = quotes.get(code)
                if not q or q.price <= 0:
                    continue

                for _, row in stock_trades.iterrows():
                    trade_price = float(row.get('成交价', 0) or 0)
                    amount = float(row.get('成交额', 0) or 0)
                    buyer = str(row.get('买方营业部', ''))
                    date_str = str(row.get('交易日期', ''))

                    if trade_price <= 0:
                        continue

                    # Calculate premium/discount vs current price
                    premium = (trade_price / q.price - 1) * 100

                    is_institution = '机构专用' in buyer
                    is_large = amount > 10_000_000  # 1000万以上

                    if is_institution and premium > 0 and is_large:
                        events.append(StockEvent(
                            code=code, name=name,
                            event_type='block_premium',
                            signal='bullish',
                            importance='high',
                            score=12,
                            summary=f"机构大宗溢价{premium:+.1f}%买入",
                            detail=f"成交价¥{trade_price:.2f} 金额¥{amount:,.0f} 买方:{buyer[:15]}",
                            date=date_str
                        ))
                    elif is_large and premium < -5:
                        events.append(StockEvent(
                            code=code, name=name,
                            event_type='block_discount',
                            signal='bearish',
                            importance='medium',
                            score=-5,
                            summary=f"大宗折价{premium:.1f}%成交",
                            detail=f"成交价¥{trade_price:.2f} 金额¥{amount:,.0f}",
                            date=date_str
                        ))
        except Exception as e:
            print(f"[Events] Block trade scan error: {e}")

        return events

    def scan_all(self) -> List[StockEvent]:
        """Run all event scans (with 12-hour cache)"""
        # Check cache
        if self._cache_path.exists():
            try:
                with open(self._cache_path) as f:
                    cached = json.load(f)
                ts = datetime.fromisoformat(cached['timestamp'])
                if datetime.now() - ts < timedelta(hours=self._cache_ttl_hours):
                    print(f"[Events] Using cache ({len(cached['events'])} events)")
                    return [StockEvent(**e) for e in cached['events']]
            except:
                pass

        codes_names = self._load_codes_names()
        if not codes_names:
            return []

        all_events = []

        print("[Events] Scanning insider trades...")
        all_events.extend(self.scan_insider_trades(codes_names))

        print("[Events] Scanning shareholder changes...")
        all_events.extend(self.scan_shareholder_changes(codes_names))

        print("[Events] Scanning block trades...")
        all_events.extend(self.scan_block_trades(codes_names))

        # Sort: high importance first, then by score
        importance_order = {'high': 0, 'medium': 1, 'low': 2}
        all_events.sort(key=lambda e: (importance_order.get(e.importance, 9), -abs(e.score)))

        # Save cache
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._cache_path, 'w') as f:
                json.dump({
                    'timestamp': datetime.now().isoformat(),
                    'events': [asdict(e) for e in all_events]
                }, f, ensure_ascii=False)
        except:
            pass

        return all_events

    def get_events_by_stock(self) -> Dict[str, List[StockEvent]]:
        """Get all events grouped by stock code (for embedding in reports)"""
        all_events = self.scan_all()
        result = {}
        for e in all_events:
            if e.code not in result:
                result[e.code] = []
            result[e.code].append(e)
        return result

    def format_stock_events(self, events: List[StockEvent], max_items: int = 5) -> List[str]:
        """Format events for a single stock (to embed in deep-dive report)
        
        Events are supplementary signals only, NOT rating factors.
        Score based on NET direction: bullish count vs bearish count.
        Total capped at ±10.
        """
        if not events:
            return []

        lines = []

        # Deduplicate: merge same person + same direction
        merged = {}
        for e in events:
            key = f"{e.event_type}_{e.summary.split('(')[0].split('增持')[0].split('减持')[0].strip()}"
            if key in merged:
                merged[key]['count'] += 1
            else:
                merged[key] = {'event': e, 'count': 1}

        # Count net direction by number of distinct actors
        bullish_items = [m for m in merged.values() if m['event'].signal == 'bullish']
        bearish_items = [m for m in merged.values() if m['event'].signal == 'bearish']

        # Net score: based on count difference, not raw score sum
        # Each bullish item = +2, each bearish item = -2, then cap at ±10
        net = len(bullish_items) * 2 - len(bearish_items) * 2
        capped_score = max(-10, min(10, net))

        if len(bullish_items) > len(bearish_items):
            signal = '🟢参考看多'
        elif len(bearish_items) > len(bullish_items):
            signal = '🔴参考看空'
        else:
            signal = '⚪中性'

        lines.append(f"**📢 近期事件** ({len(merged)}项, {signal} 增{len(bullish_items)}减{len(bearish_items)}, 仅供参考):")

        shown = 0
        for m in sorted(merged.values(), key=lambda x: (-1 if x['event'].signal == 'bullish' else 1, -x['count']))[:max_items]:
            e = m['event']
            emoji = '🟢' if e.signal == 'bullish' else '🔴'
            count_str = f" ×{m['count']}" if m['count'] > 1 else ""
            lines.append(f"- {emoji} {e.summary}{count_str} [{e.date}]")
            shown += 1

        if len(merged) > shown:
            lines.append(f"- ... 还有{len(merged)-shown}项")

        return lines

    def format_report(self, events: List[StockEvent]) -> str:
        """Format events as markdown report"""
        lines = []
        lines.append(f"# 📢 个股事件扫描")
        lines.append(f"**{datetime.now():%Y-%m-%d %H:%M}** | 增减持 + 股东变动")
        lines.append("")

        if not events:
            lines.append("✅ 无重要事件信号")
            return '\n'.join(lines)

        bullish = [e for e in events if e.signal == 'bullish']
        bearish = [e for e in events if e.signal == 'bearish']

        if bullish:
            lines.append(f"## 🟢 利好事件 ({len(bullish)})")
            lines.append("")
            for e in bullish:
                emoji = '🔥' if e.importance == 'high' else '📌'
                lines.append(f"- {emoji} **{e.name}** ({e.code}) — {e.summary}")
                lines.append(f"  {e.detail} | {e.date}")
            lines.append("")

        if bearish:
            lines.append(f"## 🔴 利空事件 ({len(bearish)})")
            lines.append("")
            for e in bearish:
                emoji = '⚠️' if e.importance == 'high' else '📌'
                lines.append(f"- {emoji} **{e.name}** ({e.code}) — {e.summary}")
                lines.append(f"  {e.detail} | {e.date}")
            lines.append("")

        # Summary score per stock
        stock_scores = {}
        for e in events:
            if e.code not in stock_scores:
                stock_scores[e.code] = {'name': e.name, 'score': 0, 'events': 0}
            stock_scores[e.code]['score'] += e.score
            stock_scores[e.code]['events'] += 1

        lines.append("## 📊 个股事件得分")
        lines.append("")
        lines.append("| 股票 | 事件数 | 得分 | 信号 |")
        lines.append("|------|--------|------|------|")
        for code, data in sorted(stock_scores.items(), key=lambda x: -x[1]['score']):
            signal = '🟢 看多' if data['score'] > 5 else '🔴 看空' if data['score'] < -5 else '⚪ 中性'
            lines.append(f"| {data['name']} | {data['events']} | {data['score']:+d} | {signal} |")

        lines.append("")
        lines.append("---")
        lines.append("_事件信号作为交易决策的补充参考，不作为独立买卖依据_")

        return '\n'.join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Stock Event Scanner')
    parser.add_argument('--send', action='store_true', help='Send to WeChat')
    args = parser.parse_args()

    scanner = EventScanner()

    try:
        print("[Events] Starting event scan...")
        t0 = time.time()
        events = scanner.scan_all()
        report = scanner.format_report(events)
        elapsed = time.time() - t0
        print(f"[Events] Done: {len(events)} events, {elapsed:.1f}s")

        if args.send and events:
            from notifier import Notifier
            n = Notifier()
            result = n.send_all(report, f"📢 事件扫描: {len(events)}个")
            print(json.dumps(result.get('_summary', {}), ensure_ascii=False))
        else:
            print(report)
    finally:
        scanner.provider.cleanup()


if __name__ == '__main__':
    main()
