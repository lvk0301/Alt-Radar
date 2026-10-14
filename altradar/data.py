"""Daily candles: download from Binance spot, cache as CSV, or load local CSV files."""

import csv
import json
import os
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone

BASE_URLS = ["https://api.binance.com", "https://data-api.binance.vision"]
STABLE_BASES = {
    "USDC", "FDUSD", "TUSD", "DAI", "USDP", "BUSD", "USDE", "USD1", "PYUSD",
    "RLUSD", "XUSD", "AEUR", "EUR", "EURI", "UST", "USTC", "PAXG", "WBTC", "BFUSD",
}
DAY_MS = 86_400_000


@dataclass
class Series:
    symbol: str
    dates: list   # "YYYY-MM-DD"
    close: list
    volume: list | None  # quote volume (USDT) per day; None when unknown

    def __len__(self):
        return len(self.dates)


def _get(path, params):
    query = urllib.parse.urlencode(params)
    last_err = None
    for base in BASE_URLS:
        try:
            with urllib.request.urlopen(f"{base}{path}?{query}", timeout=20) as r:
                return json.load(r)
        except Exception as e:  # try the next mirror
            last_err = e
    raise RuntimeError(f"Không tải được {path} từ Binance: {last_err}")


def usdt_symbols():
    """All Binance spot USDT pairs that are trading, minus stablecoins and leveraged tokens."""
    info = _get("/api/v3/exchangeInfo", {"permissions": "SPOT"})
    out = []
    for s in info["symbols"]:
        base = s["baseAsset"]
        if (s["status"] == "TRADING" and s["quoteAsset"] == "USDT"
                and base not in STABLE_BASES
                and not base.endswith(("UP", "DOWN", "BULL", "BEAR"))):
            out.append(s["symbol"])
    return sorted(out)


def fetch_daily(symbol, days=400, include_today=False):
    """Download up to `days` daily candles. The still-forming candle is dropped unless include_today."""
    now_ms = int(time.time() * 1000)
    start = now_ms - days * DAY_MS
    rows = []
    while True:
        batch = _get("/api/v3/klines", {
            "symbol": symbol, "interval": "1d", "startTime": start, "limit": 1000,
        })
        rows += batch
        if len(batch) < 1000:
            break
        start = batch[-1][0] + DAY_MS
    if not include_today:
        rows = [r for r in rows if r[6] < now_ms]
    dates = [datetime.fromtimestamp(r[0] / 1000, timezone.utc).date().isoformat() for r in rows]
    return Series(symbol, dates, [float(r[4]) for r in rows], [float(r[7]) for r in rows])


def load_csv(path):
    """CSV with columns date, close, quote_volume (quote_volume may be blank)."""
    dates, close, vol = [], [], []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            dates.append(row["date"])
            close.append(float(row["close"]))
            vol.append(float(row["quote_volume"]) if row.get("quote_volume") else None)
    symbol = os.path.splitext(os.path.basename(path))[0]
    return Series(symbol, dates, close, None if any(x is None for x in vol) else vol)


def save_csv(series, path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "close", "quote_volume"])
        for i, d in enumerate(series.dates):
            w.writerow([d, series.close[i], "" if series.volume is None else series.volume[i]])


def load_dir(path):
    """Load every *.csv in a folder, keyed by symbol."""
    return {s.symbol: s for s in
            (load_csv(os.path.join(path, f)) for f in sorted(os.listdir(path)) if f.endswith(".csv"))}


def align(coin, btc):
    """Restrict both series to the dates they share, so index t means the same day in each."""
    common = sorted(set(coin.dates) & set(btc.dates))

    def pick(s):
        idx = {d: i for i, d in enumerate(s.dates)}
        ii = [idx[d] for d in common]
        vol = None if s.volume is None else [s.volume[i] for i in ii]
        return Series(s.symbol, common, [s.close[i] for i in ii], vol)

    return pick(coin), pick(btc)
