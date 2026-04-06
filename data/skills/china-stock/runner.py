#!/usr/bin/env python3
"""
Stock Report Runner - Cron Job Entry Point

Used by OpenClaw Cron scheduler. All actions use the
stock_data + analyzers architecture.

Usage:
    python runner.py morning    # 早盘简报 (9:00)
    python runner.py midday     # 午盘快报 (11:35)
    python runner.py close      # 收盘总结 (15:05)
    python runner.py alert      # 价格预警 (每30分钟)
    python runner.py weekly     # 周报 (周六10:00)
"""

import argparse
import json
import sys
import traceback
from datetime import datetime, date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from stock_data import get_provider, StockQuote, parse_watchlist
from analyzers import MasterAnalyzer
from notifier import Notifier


class TradingCalendar:
    """中国A股交易日历，使用新浪接口获取真实交易日（含节假日排除）"""

    CACHE_PATH = Path('/home/node/.openclaw/stock-data/cache/trading_calendar.json')

    @classmethod
    def _load_cache(cls) -> set:
        if cls.CACHE_PATH.exists():
            try:
                with open(cls.CACHE_PATH) as f:
                    data = json.load(f)
                # Check if cache covers current year
                if str(datetime.now().year) in data.get('years', []):
                    return set(data.get('dates', []))
            except:
                pass
        return set()

    @classmethod
    def _save_cache(cls, dates: set):
        cls.CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        years = sorted(set(d[:4] for d in dates))
        with open(cls.CACHE_PATH, 'w') as f:
            json.dump({'years': years, 'dates': sorted(dates), 'updated': datetime.now().isoformat()}, f)

    @classmethod
    def _fetch_from_sina(cls) -> set:
        """从新浪获取交易日历"""
        try:
            import akshare as ak
            df = ak.tool_trade_date_hist_sina()
            dates = set(df['trade_date'].astype(str).tolist())
            cls._save_cache(dates)
            return dates
        except Exception as e:
            print(f"[Calendar] Failed to fetch: {e}")
            return set()

    @classmethod
    def get_trading_dates(cls) -> set:
        """获取所有交易日（带缓存）"""
        dates = cls._load_cache()
        if not dates:
            dates = cls._fetch_from_sina()
        return dates

    @classmethod
    def is_trading_day(cls, d: date = None) -> bool:
        """判断是否为交易日（考虑节假日）"""
        if d is None:
            d = date.today()

        # Weekend shortcut
        if d.weekday() >= 5:
            return False

        dates = cls.get_trading_dates()
        if dates:
            return str(d) in dates
        else:
            # Fallback: weekday only (if API fails)
            return d.weekday() < 5


class StockReportRunner:
    """Stock report runner for cron jobs"""

    def __init__(self):
        self.provider = get_provider()
        self.analyzer = MasterAnalyzer()
        self.notifier = Notifier()
        self.watchlist_file = Path('/home/node/.openclaw/stock-data/watchlist.json')
        self.log_dir = Path('/home/node/.openclaw/stock-data/logs')
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def log(self, level: str, msg: str):
        line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] [{level.upper()}] {msg}"
        print(line)
        log_file = self.log_dir / f"stock-{datetime.now():%Y%m%d}.log"
        with open(log_file, 'a') as f:
            f.write(line + '\n')

    def load_watchlist(self) -> dict:
        if self.watchlist_file.exists():
            with open(self.watchlist_file) as f:
                return json.load(f)
        return {'groups': {}, 'alerts': {}}

    def get_all_codes(self) -> list:
        wl = self.load_watchlist()
        codes = []
        for stocks in parse_watchlist(wl).values():
            for s in stocks:
                codes.append(s['code'] if isinstance(s, dict) else s)
        return codes

    def is_trading_day(self) -> bool:
        """判断今天是否为A股交易日（排除周末+法定节假日）"""
        return TradingCalendar.is_trading_day()

    def is_trading_hours(self) -> bool:
        t = datetime.now().hour * 100 + datetime.now().minute
        return (930 <= t <= 1130) or (1300 <= t <= 1500)

    # ===== Actions =====

    def run_morning(self) -> dict:
        """早盘简报"""
        self.log('info', '生成早盘简报...')
        if not self.is_trading_day():
            self.log('info', '非交易日，跳过')
            return {'status': 'skipped'}

        try:
            codes = self.get_all_codes()
            quotes = self.provider.get_quotes(codes)
            wl = self.load_watchlist()

            lines = [
                f"# 🌅 早盘简报 - {datetime.now():%Y-%m-%d %A}",
                f"> 更新: {datetime.now():%H:%M}",
                "",
                "## 📊 自选股行情",
                ""
            ]

            for name, stocks in parse_watchlist(wl).items():
                lines.append(f"**{name}:**")
                for s in stocks:
                    code = s['code'] if isinstance(s, dict) else s
                    sname = s.get('name', code) if isinstance(s, dict) else code
                    q = quotes.get(code)
                    if q:
                        e = "🟢" if q.change_pct >= 0 else "🔴"
                        lines.append(f"- {sname}: ¥{q.price:.2f} {e}{q.change_pct:+.2f}%")
                    else:
                        lines.append(f"- {sname}: 无数据")
                lines.append("")

            alerts = wl.get('alerts', {})
            if alerts:
                lines.append("## 🔔 今日预警设置")
                for code, cfg in alerts.items():
                    n = cfg.get('name', code)
                    if 'priceAbove' in cfg:
                        lines.append(f"- {n}: 突破 ¥{cfg['priceAbove']}")
                    if 'priceBelow' in cfg:
                        lines.append(f"- {n}: 跌破 ¥{cfg['priceBelow']}")

            report = '\n'.join(lines)
            result = self.notifier.send_all(report, f"🌅 早盘简报 - {datetime.now():%m/%d}")
            self.log('info', '早盘简报已发送')
            return {'status': 'success', 'result': result}

        except Exception as e:
            self.log('error', f'早盘简报失败: {e}\n{traceback.format_exc()}')
            return {'status': 'error', 'error': str(e)}

    def run_midday(self) -> dict:
        """午盘快报"""
        self.log('info', '生成午盘快报...')
        if not self.is_trading_day():
            return {'status': 'skipped'}

        try:
            codes = self.get_all_codes()
            quotes = self.provider.get_quotes(codes)
            sorted_q = sorted(quotes.values(), key=lambda q: q.change_pct, reverse=True)

            lines = [f"# 🕛 午盘快报 - {datetime.now():%m-%d %H:%M}", "", "## 🚀 领涨", ""]
            for q in sorted_q[:3]:
                lines.append(f"- {q.name} ({q.code}): ¥{q.price:.2f} 🟢{q.change_pct:+.2f}%")

            lines.extend(["", "## 📉 领跌", ""])
            for q in sorted_q[-3:]:
                lines.append(f"- {q.name} ({q.code}): ¥{q.price:.2f} 🔴{q.change_pct:+.2f}%")

            report = '\n'.join(lines)
            result = self.notifier.send_all(report, f"🕛 午盘快报 - {datetime.now():%m/%d}")
            self.log('info', '午盘快报已发送')
            return {'status': 'success', 'result': result}

        except Exception as e:
            self.log('error', f'午盘快报失败: {e}')
            return {'status': 'error', 'error': str(e)}

    def run_close(self) -> dict:
        """收盘总结"""
        self.log('info', '生成收盘总结...')
        if not self.is_trading_day():
            return {'status': 'skipped'}

        try:
            from report import DeepDiveReport
            rpt = DeepDiveReport()
            report = rpt.generate()
            result = self.notifier.send_all(report, f"📊 收盘总结 - {datetime.now():%m/%d}")
            self.log('info', '收盘总结已发送')
            return {'status': 'success', 'result': result}

        except Exception as e:
            self.log('error', f'收盘总结失败: {e}\n{traceback.format_exc()}')
            return {'status': 'error', 'error': str(e)}

    def run_alert(self) -> dict:
        """价格预警"""
        self.log('info', '检查价格预警...')
        if not self.is_trading_day() or not self.is_trading_hours():
            return {'status': 'skipped'}

        try:
            wl = self.load_watchlist()
            alerts_cfg = wl.get('alerts', {})
            if not alerts_cfg:
                return {'status': 'success', 'alerts': 0}

            quotes = self.provider.get_quotes(list(alerts_cfg.keys()))
            triggered = []

            for code, cfg in alerts_cfg.items():
                q = quotes.get(code)
                if not q:
                    continue
                name = cfg.get('name', q.name or code)

                if 'priceAbove' in cfg and q.price > cfg['priceAbove']:
                    triggered.append(f"⚠️ {name} 突破 ¥{cfg['priceAbove']}，当前 ¥{q.price:.2f}")
                if 'priceBelow' in cfg and q.price < cfg['priceBelow']:
                    triggered.append(f"⚠️ {name} 跌破 ¥{cfg['priceBelow']}，当前 ¥{q.price:.2f}")
                if 'changePctAbove' in cfg and abs(q.change_pct) > cfg['changePctAbove']:
                    triggered.append(f"⚠️ {name} 波动 {q.change_pct:+.2f}%")

            if triggered:
                report = f"# ⚠️ 价格预警 - {datetime.now():%H:%M}\n\n" + '\n'.join(triggered)
                result = self.notifier.send_all(report, "⚠️ 股票价格预警")
                self.log('info', f'已触发 {len(triggered)} 条预警')
                return {'status': 'success', 'alerts': len(triggered), 'result': result}

            self.log('info', '无预警触发')
            return {'status': 'success', 'alerts': 0}

        except Exception as e:
            self.log('error', f'预警检查失败: {e}')
            return {'status': 'error', 'error': str(e)}

    def run_weekly(self) -> dict:
        """周报"""
        self.log('info', '生成周报...')
        try:
            from report import DeepDiveReport
            rpt = DeepDiveReport()
            report = rpt.generate()
            result = self.notifier.send_all(report, f"📊 股票周报 - {datetime.now():%Y年第%W周}")
            self.log('info', '周报已发送')
            return {'status': 'success', 'result': result}

        except Exception as e:
            self.log('error', f'周报失败: {e}\n{traceback.format_exc()}')
            return {'status': 'error', 'error': str(e)}


def main():
    parser = argparse.ArgumentParser(description='Stock Report Runner')
    parser.add_argument('action', choices=['morning', 'midday', 'close', 'alert', 'weekly', 'test'])
    args = parser.parse_args()

    runner = StockReportRunner()

    actions = {
        'morning': runner.run_morning,
        'midday': runner.run_midday,
        'close': runner.run_close,
        'alert': runner.run_alert,
        'weekly': runner.run_weekly,
    }

    if args.action == 'test':
        print("🧪 Testing components...\n")
        codes = runner.get_all_codes()
        print(f"1. Watchlist: {len(codes)} stocks")

        quotes = runner.provider.get_quotes(codes[:4])
        print(f"2. Quotes: {len(quotes)} fetched")
        for q in quotes.values():
            print(f"   {q.name} ({q.code}): ¥{q.price:.2f} {q.change_pct:+.2f}%")

        print(f"\n3. Notifier channels: {list(runner.notifier.config.keys())}")
        print("\n✅ Test complete!")
        result = {'status': 'test_ok'}
    else:
        result = actions[args.action]()

    runner.provider.cleanup()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
