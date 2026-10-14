"""Walk through history day by day and check what happened after each signal.

For every coin-day the radar scores without looking ahead. A signal is counted on the day a
coin first enters "sẵn sàng", or first triggers, then that state is muted for the coin for
`cooldown` days so one setup is not counted many times. The result is compared with all coin-days scored, to
show whether the signals did better than picking a day at random.
"""

from dataclasses import dataclass

from .data import align
from .indicators import median
from .phases import pump_legs
from .rules import CFG, STATE_NODATA, STATE_READY, STATE_TRIGGER, STATE_WAIT, assess


@dataclass
class Outcome:
    symbol: str
    date: str
    state: str
    score: float
    max_gain: float   # best close within the horizon vs. the signal close
    end_gain: float   # close at the end of the horizon vs. the signal close


def run(coins, btc, horizon=14, cooldown=10, cfg=CFG, progress=None):
    legs_cache = {}  # coins that start on the same day share the same aligned BTC series

    signals, all_days = [], []
    for n, coin in enumerate(coins.values()):
        if progress:
            progress(n, len(coins), coin.symbol)
        c, b = align(coin, btc)

        def legs_at(d, b=b):
            key = (b.dates[0], d)
            if key not in legs_cache:
                legs_cache[key] = pump_legs(b.close[:d + 1], cfg.btc_leg_gain, cfg.btc_leg_window)
            return legs_cache[key]

        muted_until = {STATE_READY: -1, STATE_TRIGGER: -1}  # ready and trigger counted separately
        for t in range(50, len(c) - horizon):
            res = assess(c, b, t, cfg, legs_at)
            if res.state in (STATE_WAIT, STATE_NODATA):
                continue
            fut = c.close[t + 1:t + horizon + 1]
            o = Outcome(c.symbol, c.dates[t], res.state, res.score,
                        max(fut) / c.close[t] - 1, fut[-1] / c.close[t] - 1)
            all_days.append(o)
            if res.state in muted_until and t > muted_until[res.state]:
                signals.append(o)
                muted_until[res.state] = t + cooldown
    return signals, all_days


def summarize(outcomes, hit=0.20):
    if not outcomes:
        return {"n": 0}
    mg = [o.max_gain for o in outcomes]
    eg = [o.end_gain for o in outcomes]
    return {
        "n": len(outcomes),
        "hit_rate": sum(1 for x in mg if x >= hit) / len(mg),
        "median_max_gain": median(mg),
        "median_end_gain": median(eg),
        "lost_10pct": sum(1 for x in eg if x <= -0.10) / len(eg),
    }
