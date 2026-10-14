"""BTC phases: find the pump legs that switch the radar on, and the quiet days between them."""

from .indicators import median, pct


def pump_legs(btc_close, min_gain=0.10, window=5):
    """Stretches where BTC's `window`-day gain is at least `min_gain`.

    Returns (start, end) index pairs: start is the lowest close in the window before the
    stretch, end is the highest close inside it. Uses only the data passed in, so calling it
    on btc_close[:t+1] never looks ahead.
    """
    legs, n, i = [], len(btc_close), window
    while i < n:
        if pct(btc_close[i - window], btc_close[i]) >= min_gain:
            j = i
            while j + 1 < n and pct(btc_close[j + 1 - window], btc_close[j + 1]) >= min_gain:
                j += 1
            lo = min(range(i - window, i + 1), key=btc_close.__getitem__)
            hi = max(range(i, j + 1), key=btc_close.__getitem__)
            legs.append((lo, hi))
            i = j + 1
        else:
            i += 1
    return legs


def leg_gain(close, leg, extra=2):
    """Best gain from the leg's start to any close up to `extra` days after the leg's end."""
    lo, hi = leg
    return max(close[lo:min(hi + extra, len(close) - 1) + 1]) / close[lo] - 1


def rest_days(legs, start, t):
    """Days in (start, t] that are not inside any pump leg: the days BTC is resting."""
    inside = {d for lo, hi in legs for d in range(lo + 1, hi + 1)}
    return [d for d in range(start + 1, t + 1) if d not in inside]


def compound(close, days):
    """Total return earned only on the given days."""
    r = 1.0
    for d in days:
        r *= close[d] / close[d - 1]
    return r - 1


def btc_regime(btc, t, legs, lookback=90):
    """What BTC is doing on day t, in the terms used by the radar."""
    b, v = btc.close, btc.volume
    recent = [L for L in legs if L[0] >= t - lookback]
    hi90 = max(b[max(0, t - lookback + 1):t + 1])
    out = {
        "radar_on": bool(recent),
        "legs": recent,
        "btc_from_high": pct(hi90, b[t]),
        "alt_window": False,
        "btc_vol_ratio": None,
    }
    if not recent:
        return out
    lo = recent[0][0]
    resting = t - recent[-1][1] >= 7
    near_high = b[t] >= 0.9 * hi90
    if v:
        base = median(v[max(0, lo - 20):lo] or v[:lo + 1])
        out["btc_vol_ratio"] = sum(v[t - 6:t + 1]) / 7 / base
        quiet = out["btc_vol_ratio"] < 1.0
    else:
        quiet = True
    out["alt_window"] = resting and near_high and quiet
    return out
