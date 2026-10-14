"""Checks against the Aug–Oct 2026 data the pattern was drawn from (tests/fixtures)."""

import os
import unittest

from altradar import backtest
from altradar.data import align, load_dir
from altradar.phases import pump_legs
from altradar.rules import STATE_EXCLUDED, STATE_READY, STATE_TRIGGER, assess, evaluate

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


class FixtureCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.coins = load_dir(FIX)
        cls.btc = cls.coins.pop("BTCUSDT")

    def at(self, symbol, date, fn=evaluate):
        c, b = align(self.coins[symbol], self.btc)
        return fn(c, b, c.dates.index(date))


class TestPhases(FixtureCase):
    def test_finds_both_btc_legs(self):
        legs = [(self.btc.dates[a], self.btc.dates[b]) for a, b in pump_legs(self.btc.close)]
        self.assertEqual(legs, [("2026-08-16", "2026-08-24"), ("2026-09-16", "2026-09-21")])

    def test_no_look_ahead(self):
        # On Sep 10 only the first leg exists yet.
        t = self.btc.dates.index("2026-09-10")
        self.assertEqual(len(pump_legs(self.btc.close[:t + 1])), 1)


class TestRules(FixtureCase):
    def test_group1_ready_day_before_breakout(self):
        for s in ("BATUSDT", "WALUSDT", "ZKUSDT", "OPUSDT"):
            r = self.at(s, "2026-10-08")
            self.assertEqual(r.state, STATE_READY, s)
            self.assertGreaterEqual(r.score, 85, s)

    def test_group3_excluded(self):
        for s in ("CASHCATUSDT", "AIARTIFIUSDT"):
            r = self.at(s, "2026-10-08")
            self.assertEqual(r.state, STATE_EXCLUDED, s)
            self.assertTrue(any(x.startswith("X3") for x in r.excluded), s)

    def test_group2_not_ready(self):
        self.assertNotEqual(self.at("QUACUSDT", "2026-10-08").state, STATE_READY)
        self.assertNotEqual(self.at("ALEOUSDT", "2026-10-08").state, STATE_READY)

    def test_triggers_on_breakout_days(self):
        self.assertEqual(self.at("BATUSDT", "2026-10-09", assess).state, STATE_TRIGGER)
        self.assertEqual(self.at("ZKUSDT", "2026-10-09", assess).state, STATE_TRIGGER)
        self.assertEqual(self.at("WALUSDT", "2026-10-14", assess).state, STATE_TRIGGER)

    def test_no_trigger_when_overheated(self):
        # BAT broke out again on Oct 11 after +60%: excluded as overheated, not a new trigger.
        self.assertNotEqual(self.at("BATUSDT", "2026-10-11", assess).state, STATE_TRIGGER)

    def test_missing_volume_rules_left_out(self):
        r = self.at("TRACUSDT", "2026-10-08")  # fixture has no volume for TRAC
        skipped = {k.code for k in r.checks if k.passed is None}
        self.assertTrue({"A2", "R2", "B5", "B6"} <= skipped)
        self.assertLessEqual(r.score, 100)

    def test_waits_before_btc_pump(self):
        c, b = align(self.coins["OPUSDT"], self.btc)
        self.assertEqual(evaluate(c, b, b.dates.index("2026-08-12")).state, "chờ BTC")


class TestBacktest(FixtureCase):
    def test_runs_and_counts(self):
        signals, days = backtest.run(self.coins, self.btc, horizon=5)
        self.assertTrue(days)
        self.assertTrue(any(o.state == STATE_TRIGGER for o in signals))
        s = backtest.summarize(signals)
        self.assertGreater(s["n"], 0)
        self.assertTrue(0 <= s["hit_rate"] <= 1)


if __name__ == "__main__":
    unittest.main()
