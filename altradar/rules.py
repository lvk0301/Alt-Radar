"""The group-1 pattern as scored rules.

A coin is scored only after BTC has made a pump leg (the radar is off before that). Rules
that need data the coin does not have (e.g. volume) are left out of the score instead of
counting as failures, so the score is always "points earned / points available * 100".
"""

from dataclasses import dataclass, field

from .indicators import max_drawdown, median, pct, rsi, sma, weekly_higher_lows
from .phases import compound, leg_gain, pump_legs, rest_days


@dataclass
class Config:
    btc_leg_gain: float = 0.10      # BTC pump leg: >= +10% ...
    btc_leg_window: int = 5         # ... within 5 days
    lookback: int = 90              # only legs that started in the last 90 days count
    wake_ratio: float = 0.6         # A1: coin gain >= 60% of BTC's gain in the first leg
    wake_vol: float = 3.0           # A2: a day with >= 3x baseline volume during that leg
    rest_tolerance: float = 0.05    # R1: coin return on BTC rest days >= BTC's - 5 points
    rest_vol: float = 2.0           # R2: average volume on rest days >= 2x baseline
    max_range20: float = 0.40       # B1
    min_days_above_sma20: int = 20  # B2 (out of 30)
    min_higher_lows: float = 4 / 9  # B3 (share of weekly comparisons)
    accum_vol: float = 2.0          # B5: 14-day average volume >= 2x baseline
    accum_days: int = 4             # B6: green days with >= 3x volume in last 30
    rsi_band: tuple = (45, 68)      # B7
    from_high_band: tuple = (-0.25, -0.03)  # B8: distance below the 90-day high
    shake_btc_drop: float = -0.04   # C: BTC fell at least 4% in the last 10 days
    shake_max_mult: float = 3.0     # C: coin fell no more than 3x BTC's fall
    breakout_gain: float = 0.10     # D2
    breakout_vol: float = 4.0       # D2
    min_quote_vol: float = 500_000  # X4: 7-day average USDT volume
    ready_score: float = 70
    forming_score: float = 50


CFG = Config()


@dataclass
class Check:
    code: str
    label: str
    points: float
    passed: bool | None   # None = not enough data, left out of the score
    detail: str = ""
    partial: float | None = None  # points earned when only part of the rule is met

    @property
    def earned(self):
        if not self.passed:
            return 0.0
        return self.points if self.partial is None else self.partial


@dataclass
class Result:
    symbol: str
    date: str
    state: str
    score: float = 0.0
    checks: list = field(default_factory=list)
    excluded: list = field(default_factory=list)
    breakout: bool = False
    info: dict = field(default_factory=dict)


STATE_WAIT = "chờ BTC"
STATE_NODATA = "thiếu dữ liệu"
STATE_EXCLUDED = "loại trừ"
STATE_TRIGGER = "KÍCH HOẠT"
STATE_READY = "sẵn sàng"
STATE_FORMING = "đang hình thành"
STATE_WEAK = "yếu"


def evaluate(coin, btc, t, cfg=CFG, legs=None):
    """Score `coin` on day index t. coin and btc must be aligned (see data.align)."""
    c, v, b = coin.close, coin.volume, btc.close
    res = Result(coin.symbol, coin.dates[t], STATE_WAIT)
    if legs is None:
        legs = pump_legs(b[:t + 1], cfg.btc_leg_gain, cfg.btc_leg_window)
    legs = [L for L in legs if L[0] >= t - cfg.lookback and L[1] <= t]
    if not legs:
        return res
    wake, last = legs[0], legs[-1]
    lo = wake[0]
    if lo < 10 or t < 50:
        res.state = STATE_NODATA
        return res

    base_from = max(0, lo - 20)
    base = median(v[base_from:lo]) if v else None
    if base is not None and base <= 0:
        base = None
    s20 = sma(c, 20, t)
    r = rsi(c, t)
    hi90 = max(c[max(0, t - 89):t + 1])
    res.info = {"price": c[t], "rsi": r, "sma20": s20, "from_high": pct(hi90, c[t]),
                "vs_btc_30d": pct(c[t - 30], c[t]) - pct(b[t - 30], b[t]),
                "vol14x": (sum(v[t - 13:t + 1]) / 14 / base) if base else None,
                "wake_leg": (btc.dates[wake[0]], btc.dates[wake[1]])}

    # --- exclusions (group 3 / overheated / illiquid)
    pre_pump = c[lo] / min(c[base_from:lo + 1]) - 1
    if c[t] < 0.5 * hi90 and c[t] < s20:
        res.excluded.append("X1 thấp hơn đỉnh 90 ngày >50% và dưới SMA20")
    if r > 80 and c[t] > 1.5 * s20:
        res.excluded.append("X2 quá nóng: RSI>80 và cao hơn SMA20 >50%")
    if pre_pump > 1.0:
        res.excluded.append(f"X3 đã pump {pre_pump:+.0%} trước khi BTC tăng")
    if v and sum(v[t - 6:t + 1]) / 7 < cfg.min_quote_vol:
        res.excluded.append("X4 thanh khoản thấp (<$500k/ngày)")

    checks = res.checks
    has_vol = base is not None

    # --- A: woke up with BTC's first leg
    btc_wake, coin_wake = leg_gain(b, wake), leg_gain(c, wake)
    checks.append(Check("A1", "Tăng theo BTC ở đợt BTC bứt phá đầu", 10,
                        coin_wake >= cfg.wake_ratio * btc_wake,
                        f"coin {coin_wake:+.0%} / BTC {btc_wake:+.0%}"))
    if has_vol:
        peak = max(v[lo:min(wake[1] + 2, t) + 1]) / base
        checks.append(Check("A2", "Khối lượng nổ trong đợt đó", 5, peak >= cfg.wake_vol, f"{peak:.1f}x"))
    else:
        checks.append(Check("A2", "Khối lượng nổ trong đợt đó", 5, None, "không có khối lượng"))

    # --- R: held up while BTC rested (the key test)
    rest = rest_days(legs, lo, t)
    if len(rest) >= 5:
        cr, br = compound(c, rest), compound(b, rest)
        checks.append(Check("R1", "Giữ giá khi BTC nghỉ", 10, cr >= br - cfg.rest_tolerance,
                            f"coin {cr:+.0%} / BTC {br:+.0%}"))
        if has_vol:
            rv = sum(v[d] for d in rest) / len(rest) / base
            checks.append(Check("R2", "Khối lượng vẫn cao khi BTC nghỉ", 10, rv >= cfg.rest_vol, f"{rv:.1f}x"))
        else:
            checks.append(Check("R2", "Khối lượng vẫn cao khi BTC nghỉ", 10, None, "không có khối lượng"))
    else:
        checks.append(Check("R1", "Giữ giá khi BTC nghỉ", 10, None, "BTC chưa nghỉ đủ lâu"))
        checks.append(Check("R2", "Khối lượng vẫn cao khi BTC nghỉ", 10, None, "BTC chưa nghỉ đủ lâu"))

    # --- L: beat BTC again on a later leg
    if len(legs) >= 2:
        bl, cl = leg_gain(b, last), leg_gain(c, last)
        checks.append(Check("L", "Mạnh hơn BTC ở đợt BTC tăng tiếp theo", 10, cl >= bl,
                            f"coin {cl:+.0%} / BTC {bl:+.0%}"))
    else:
        checks.append(Check("L", "Mạnh hơn BTC ở đợt BTC tăng tiếp theo", 10, None, "chưa có đợt 2"))

    # --- B: base structure
    rng = max(c[t - 19:t + 1]) / min(c[t - 19:t + 1]) - 1
    checks.append(Check("B1", "Nền giá hẹp (biên độ 20 ngày)", 5, rng <= cfg.max_range20, f"{rng:.0%}"))
    hl, n_cmp = weekly_higher_lows(c, t)
    checks.append(Check("B3", "Đáy tuần cao dần", 5, n_cmp > 0 and hl / n_cmp >= cfg.min_higher_lows,
                        f"{hl}/{n_cmp}"))
    above = sum(1 for d in range(t - 29, t + 1) if c[d] > sma(c, 20, d))
    checks.append(Check("B2", "Nằm trên SMA20", 5, above >= cfg.min_days_above_sma20, f"{above}/30 ngày"))
    rs = res.info["vs_btc_30d"]
    checks.append(Check("B4", "Mạnh hơn BTC 30 ngày", 5, rs > 0, f"{rs * 100:+.0f} điểm"))

    # --- V: accumulation volume
    if has_vol:
        v14 = res.info["vol14x"]
        green3 = sum(1 for d in range(t - 29, t + 1) if v[d] >= 3 * base and c[d] > c[d - 1])
        checks.append(Check("B5", "Khối lượng 14 ngày tăng", 7.5, v14 >= cfg.accum_vol, f"{v14:.1f}x"))
        checks.append(Check("B6", "Ngày xanh khối lượng ≥3x", 7.5, green3 >= cfg.accum_days, f"{green3} ngày"))
    else:
        checks.append(Check("B5", "Khối lượng 14 ngày tăng", 7.5, None, "không có khối lượng"))
        checks.append(Check("B6", "Ngày xanh khối lượng ≥3x", 7.5, None, "không có khối lượng"))

    # --- H: not overheated, still room
    checks.append(Check("B7", "RSI chưa nóng", 5, cfg.rsi_band[0] <= r <= cfg.rsi_band[1], f"RSI {r:.0f}"))
    fh = res.info["from_high"]
    checks.append(Check("B8", "Còn cách đỉnh", 5, cfg.from_high_band[0] <= fh <= cfg.from_high_band[1],
                        f"{fh:+.0%}"))

    # --- C: shakeout on a BTC dip in the last 10 days
    w0 = t - 9
    btc_dd = max_drawdown(b, w0, t)
    if btc_dd <= cfg.shake_btc_drop:
        coin_dd = max_drawdown(c, w0, t)
        held = min(c[w0:t + 1]) >= min(c[t - 29:w0])
        ok = held and coin_dd >= cfg.shake_max_mult * btc_dd
        recovered = c[t] > s20
        checks.append(Check("C", "Rũ hàng khi BTC giảm rồi giữ nền", 10, ok,
                            f"coin {coin_dd:+.0%} / BTC {btc_dd:+.0%}"
                            + ("" if not ok else ", đã hồi trên SMA20" if recovered else ", chưa hồi"),
                            partial=None if recovered else 5))  # held but not recovered yet: half
    else:
        checks.append(Check("C", "Rũ hàng khi BTC giảm rồi giữ nền", 10, None, "BTC không giảm gần đây"))

    avail = sum(k.points for k in checks if k.passed is not None)
    earned = sum(k.earned for k in checks)
    res.score = 100 * earned / avail if avail else 0.0

    # --- D: breakout candle today
    day = pct(c[t - 1], c[t])
    res.breakout = (c[t] > max(c[t - 20:t]) and day >= cfg.breakout_gain
                    and (not has_vol or v[t] >= cfg.breakout_vol * base)
                    and pct(b[t - 1], b[t]) > -0.02)

    if res.excluded:
        res.state = STATE_EXCLUDED
    elif res.score >= cfg.ready_score:
        res.state = STATE_READY
    elif res.score >= cfg.forming_score:
        res.state = STATE_FORMING
    else:
        res.state = STATE_WEAK
    return res


def assess(coin, btc, t, cfg=CFG, legs_at=None):
    """evaluate() plus the trigger: a breakout today by a coin that was ready yesterday."""
    get = (lambda d: legs_at(d)) if legs_at else (lambda d: None)
    today = evaluate(coin, btc, t, cfg, get(t))
    if today.breakout and not today.excluded:  # no chasing an overheated re-breakout
        prev = evaluate(coin, btc, t - 1, cfg, get(t - 1))
        if prev.state == STATE_READY:
            today.state = STATE_TRIGGER
            today.info["score_yesterday"] = prev.score
    return today
