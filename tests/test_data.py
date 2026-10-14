"""Binance parsing, with the HTTP call replaced so the test runs offline."""

import time
import unittest
from unittest import mock

from altradar import data

DAY = data.DAY_MS


def kline(open_ms, close, quote_vol):
    return [open_ms, "1", "1", "1", str(close), "100", open_ms + DAY - 1, str(quote_vol), 0, "0", "0", "0"]


class TestBinance(unittest.TestCase):
    def test_fetch_daily_drops_forming_candle(self):
        today = int(time.time() * 1000) // DAY * DAY
        rows = [kline(today - 2 * DAY, 1.5, 1000), kline(today - DAY, 1.6, 2000), kline(today, 1.7, 50)]
        with mock.patch.object(data, "_get", return_value=rows):
            s = data.fetch_daily("OPUSDT", days=3)
        self.assertEqual(s.close, [1.5, 1.6])
        self.assertEqual(s.volume, [1000.0, 2000.0])
        self.assertEqual(len(s.dates), 2)

    def test_usdt_symbols_filters(self):
        info = {"symbols": [
            {"symbol": "OPUSDT", "baseAsset": "OP", "quoteAsset": "USDT", "status": "TRADING"},
            {"symbol": "USDCUSDT", "baseAsset": "USDC", "quoteAsset": "USDT", "status": "TRADING"},
            {"symbol": "BTCUPUSDT", "baseAsset": "BTCUP", "quoteAsset": "USDT", "status": "TRADING"},
            {"symbol": "OPBTC", "baseAsset": "OP", "quoteAsset": "BTC", "status": "TRADING"},
            {"symbol": "LUNAUSDT", "baseAsset": "LUNA", "quoteAsset": "USDT", "status": "BREAK"},
        ]}
        with mock.patch.object(data, "_get", return_value=info):
            self.assertEqual(data.usdt_symbols(), ["OPUSDT"])


if __name__ == "__main__":
    unittest.main()
