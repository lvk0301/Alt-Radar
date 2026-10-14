"""Command line: scan / explain / backtest.

    python -m altradar scan                      # quét tất cả cặp USDT trên Binance
    python -m altradar explain OPUSDT            # giải thích từng điều kiện của 1 coin
    python -m altradar backtest --days 900       # kiểm tra ngược trên dữ liệu quá khứ
    python -m altradar scan --data tests/fixtures --date 2026-10-08   # chạy offline từ CSV
"""

import argparse
import os
import sys

from . import backtest, data
from .phases import btc_regime, pump_legs
from .rules import (CFG, STATE_EXCLUDED, STATE_FORMING, STATE_READY, STATE_TRIGGER,
                    STATE_WEAK, assess)

CACHE = ".cache"
ORDER = {STATE_TRIGGER: 0, STATE_READY: 1, STATE_FORMING: 2, STATE_WEAK: 3, STATE_EXCLUDED: 4}


def load(args, symbols=None):
    """Return (btc, {symbol: Series}) from --data CSVs or from Binance (cached per day)."""
    if args.data:
        coins = data.load_dir(args.data)
        btc = coins.pop("BTCUSDT")
        if symbols:
            coins = {s: coins[s] for s in symbols}
        return btc, coins

    symbols = symbols or data.usdt_symbols()
    btc = _cached("BTCUSDT", args.days)
    coins = {}
    for n, s in enumerate(symbols):
        if s == "BTCUSDT":
            continue
        print(f"\rTải dữ liệu {n + 1}/{len(symbols)} {s:<14}", end="", file=sys.stderr)
        try:
            coins[s] = _cached(s, args.days)
        except RuntimeError as e:
            print(f"\n  bỏ qua {s}: {e}", file=sys.stderr)
    print(file=sys.stderr)
    return btc, coins


def _cached(symbol, days):
    path = os.path.join(CACHE, f"{symbol}_{days}.csv")
    if os.path.exists(path) and _fresh(path):
        return data.load_csv(path)
    s = data.fetch_daily(symbol, days)
    data.save_csv(s, path)
    return s


def _fresh(path, hours=6):
    import time
    return time.time() - os.path.getmtime(path) < hours * 3600


def _day_index(series, date):
    if date is None:
        return len(series) - 1
    if date not in series.dates:
        sys.exit(f"Không có dữ liệu ngày {date}")
    return series.dates.index(date)


def _fmt_pct(x):
    return "-" if x is None else f"{x * 100:+.0f}%"


def print_regime(btc, t):
    legs = pump_legs(btc.close[:t + 1], CFG.btc_leg_gain, CFG.btc_leg_window)
    reg = btc_regime(btc, t, legs, CFG.lookback)
    print(f"BTC ngày {btc.dates[t]}: {btc.close[t]:,.0f}  (cách đỉnh 90 ngày {_fmt_pct(reg['btc_from_high'])})")
    if not reg["radar_on"]:
        print("  Radar TẮT: BTC chưa có đợt tăng ≥10% trong 5 ngày trong 90 ngày qua.")
        return reg
    for lo, hi in reg["legs"]:
        print(f"  Đợt BTC tăng: {btc.dates[lo]} → {btc.dates[hi]}  ({_fmt_pct(btc.close[hi] / btc.close[lo] - 1)})")
    if reg["btc_vol_ratio"] is not None:
        print(f"  Khối lượng BTC 7 ngày: {reg['btc_vol_ratio']:.1f}x mức nền")
    print("  >>> CỬA SỔ MÙA ALT: BTC đứng im ở vùng cao, khối lượng BTC giảm" if reg["alt_window"]
          else "  Chưa phải cửa sổ mùa alt (cần BTC nghỉ ≥7 ngày, gần đỉnh, khối lượng BTC < 1x).")
    return reg


def cmd_scan(args):
    btc, coins = load(args, args.symbols)
    t_btc = _day_index(btc, args.date)
    print_regime(btc, t_btc)
    rows = []
    for coin in coins.values():
        c, b = data.align(coin, btc)
        if btc.dates[t_btc] not in c.dates:
            continue
        t = c.dates.index(btc.dates[t_btc])
        if t < 51:
            continue
        r = assess(c, b, t)
        if r.state in ORDER:
            rows.append(r)
    rows.sort(key=lambda r: (ORDER[r.state], -r.score))
    if not args.all:
        rows = [r for r in rows if r.state in (STATE_TRIGGER, STATE_READY, STATE_FORMING)]
    print()
    print(f"{'Coin':<14}{'Trạng thái':<17}{'Điểm':>5}{'Giá':>13}{'RSI':>5}{'vs BTC 30n':>11}"
          f"{'Cách đỉnh':>10}{'KL 14n':>8}  Điều kiện chưa đạt")
    for r in rows[:args.top]:
        i = r.info
        missing = " ".join(k.code for k in r.checks if k.passed is False)
        vol = "-" if i.get("vol14x") is None else f"{i['vol14x']:.1f}x"
        print(f"{r.symbol:<14}{r.state:<17}{r.score:5.0f}{i['price']:13.6g}{i['rsi']:5.0f}"
              f"{i['vs_btc_30d'] * 100:+10.0f} {_fmt_pct(i['from_high']):>9}{vol:>8}  "
              f"{missing or '-'}{'  | ' + '; '.join(r.excluded) if r.excluded else ''}")
    if not rows:
        print("(không có coin nào đạt)")
    print("\nĐây là công cụ tham khảo kỹ thuật, không phải lời khuyên đầu tư.")


def cmd_explain(args):
    btc, coins = load(args, [args.symbol])
    c, b = data.align(coins[args.symbol], btc)
    t = _day_index(c, args.date)
    print_regime(b, t)
    r = assess(c, b, t)
    print(f"\n{r.symbol} ngày {r.date}: {r.state.upper()}  —  {r.score:.0f}/100 điểm")
    for k in r.checks:
        mark = "✓" if k.passed else "·" if k.passed is None else "✗"
        pts = f"{k.earned:g}/{k.points:g}" if k.passed is not None else "bỏ qua"
        print(f"  {mark} {k.code:<3}{k.label:<40}{pts:>8}   {k.detail}")
    for x in r.excluded:
        print(f"  ⛔ {x}")
    if r.breakout:
        print("  ★ Hôm nay có nến bứt phá (vượt đỉnh 20 ngày, ≥+10%, khối lượng ≥4x)")


def cmd_backtest(args):
    btc, coins = load(args, args.symbols)
    prog = lambda n, total, s: print(f"\rBacktest {n + 1}/{total} {s:<14}", end="", file=sys.stderr)
    signals, days = backtest.run(coins, btc, args.horizon, args.cooldown, progress=prog)
    print(file=sys.stderr)
    legs = pump_legs(btc.close, CFG.btc_leg_gain, CFG.btc_leg_window)
    print(f"Các đợt BTC tăng ≥10%/5 ngày trong dữ liệu ({btc.dates[0]} → {btc.dates[-1]}):")
    for lo, hi in legs:
        print(f"  {btc.dates[lo]} → {btc.dates[hi]}  {_fmt_pct(btc.close[hi] / btc.close[lo] - 1)}")

    def show(name, outs):
        s = backtest.summarize(outs)
        if not s["n"]:
            print(f"  {name:<34} không có")
            return
        print(f"  {name:<34}{s['n']:>7}{s['hit_rate'] * 100:>10.0f}%{s['median_max_gain'] * 100:>+12.0f}%"
              f"{s['median_end_gain'] * 100:>+12.0f}%{s['lost_10pct'] * 100:>10.0f}%")

    print(f"\nKết quả trong {args.horizon} ngày sau tín hiệu:")
    print(f"  {'':<34}{'Số lần':>7}{'Tăng≥20%':>11}{'Đỉnh (TV)':>13}{'Cuối kỳ (TV)':>13}{'Lỗ≥10%':>11}")
    show("Tất cả ngày (so sánh)", days)
    show("Tín hiệu 'sẵn sàng'", [o for o in signals if o.state == STATE_READY])
    show("Tín hiệu 'KÍCH HOẠT'", [o for o in signals if o.state == STATE_TRIGGER])
    if args.list:
        print("\nDanh sách tín hiệu:")
        for o in signals:
            print(f"  {o.date} {o.symbol:<14}{o.state:<12}{o.score:4.0f}  đỉnh {_fmt_pct(o.max_gain)}  cuối {_fmt_pct(o.end_gain)}")
    print("\nTăng≥20% = giá cao nhất trong kỳ vượt +20% so với ngày tín hiệu. TV = trung vị."
          "\nLỗ≥10% = giá cuối kỳ thấp hơn ngày tín hiệu từ 10% trở lên.")


def main(argv=None):
    p = argparse.ArgumentParser(prog="altradar", description="Radar tìm altcoin theo mô hình nhóm 1")
    p.add_argument("--data", help="thư mục CSV (date,close,quote_volume) thay cho Binance; phải có BTCUSDT.csv")
    p.add_argument("--days", type=int, default=400, help="số ngày lịch sử tải từ Binance (mặc định 400)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="quét và xếp hạng coin")
    s.add_argument("--symbols", type=lambda x: x.upper().split(","), help="danh sách, vd OPUSDT,ZKUSDT")
    s.add_argument("--date", help="ngày đánh giá YYYY-MM-DD (mặc định: ngày gần nhất)")
    s.add_argument("--top", type=int, default=40)
    s.add_argument("--all", action="store_true", help="hiện cả coin yếu và bị loại")
    s.set_defaults(func=cmd_scan)

    e = sub.add_parser("explain", help="giải thích từng điều kiện của 1 coin")
    e.add_argument("symbol", type=str.upper)
    e.add_argument("--date")
    e.set_defaults(func=cmd_explain)

    b = sub.add_parser("backtest", help="kiểm tra ngược")
    b.add_argument("--symbols", type=lambda x: x.upper().split(","))
    b.add_argument("--horizon", type=int, default=14, help="số ngày theo dõi sau tín hiệu")
    b.add_argument("--cooldown", type=int, default=10, help="số ngày bỏ qua tín hiệu lặp của cùng coin")
    b.add_argument("--list", action="store_true", help="in từng tín hiệu")
    b.set_defaults(func=cmd_backtest)

    args = p.parse_args(argv)
    args.func(args)
