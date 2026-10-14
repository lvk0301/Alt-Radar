"""Small indicator helpers on plain lists. `i` is always the index of the day being evaluated."""


def pct(a, b):
    return b / a - 1


def sma(x, n, i):
    return sum(x[i - n + 1:i + 1]) / n


def median(xs):
    xs = sorted(xs)
    m = len(xs) // 2
    return xs[m] if len(xs) % 2 else (xs[m - 1] + xs[m]) / 2


def rsi(x, i, n=14):
    """Wilder RSI of x[:i+1]."""
    gains = [max(x[k] - x[k - 1], 0) for k in range(1, i + 1)]
    losses = [max(x[k - 1] - x[k], 0) for k in range(1, i + 1)]
    if len(gains) < n:
        return 50.0
    ag, al = sum(gains[:n]) / n, sum(losses[:n]) / n
    for g, l in zip(gains[n:], losses[n:]):
        ag, al = (ag * (n - 1) + g) / n, (al * (n - 1) + l) / n
    return 100.0 if al == 0 else 100 - 100 / (1 + ag / al)


def max_drawdown(x, a, b):
    """Worst fall from a running peak inside x[a:b+1] (negative number)."""
    peak, dd = x[a], 0.0
    for v in x[a:b + 1]:
        peak = max(peak, v)
        dd = min(dd, v / peak - 1)
    return dd


def weekly_higher_lows(x, i, weeks=10):
    """How many of the last `weeks` 7-day blocks made a higher low than the block before."""
    n = min(weeks, (i + 1) // 7)
    lows = [min(x[i - 7 * (n - k) + 1:i - 7 * (n - k - 1) + 1]) for k in range(n)]
    return sum(1 for a, b in zip(lows, lows[1:]) if b > a), max(n - 1, 0)
