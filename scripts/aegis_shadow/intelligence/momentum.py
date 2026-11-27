"""Volatility-normalized trend evidence from completed daily bars."""
from math import log, sqrt
from statistics import mean, pstdev


def describe(closes, highs, lows, volumes, benchmark):
    if len(closes) < 61 or len(benchmark) != len(closes):
        return None
    returns = [log(right / left) for left, right in zip(closes, closes[1:])]
    volatility = pstdev(returns[-60:])
    if volatility <= 0:
        return None
    short, medium, long = (sum(returns[-n:]) / (volatility * sqrt(n)) for n in (5, 20, 60))
    market = log(benchmark[-1] / benchmark[-21])
    relative = (sum(returns[-20:]) - market) / (volatility * sqrt(20))
    persistence = sum(value > 0 for value in returns[-20:]) / 20
    high = max(highs[-21:-1])
    prior_high = max(highs[-22:-2])
    ranges = [max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
              for i in range(1, len(closes))]
    atr = mean(ranges[-14:])
    trend = mean(closes[-20:])
    pullback = long > 0 and closes[-2] < mean(closes[-7:-2]) and closes[-1] > closes[-2]
    flags = {
        "early": short > 0 >= medium,
        "small_persistent": 0 < medium <= 1 and persistence > .5,
        "accelerating": short > medium > long >= 0,
        "high": medium > 1 and long > 1,
        "exhaustion": long > 0 > short,
        "risk_adjusted": medium > 0 and long > 0,
        "relative_strength": relative > 0,
        "pullback_continuation": pullback,
        "breakout": closes[-1] > high,
        "failed_breakout": closes[-2] > prior_high and closes[-1] < prior_high,
        "volatility_compression": mean(ranges[-5:]) < mean(ranges[-25:-5]) and medium > 0,
    }
    return {"momentum_short": short, "momentum_medium": medium, "momentum_long": long,
            "daily_volatility": volatility, "relative_strength": relative, "positive_day_share": persistence,
            "atr14": atr, "trend_reference": trend, "trend_support": min(lows[-10:]),
            "chandelier_high": max(highs[-22:]), "breakout_level": high,
            "liquidity_proxy": closes[-1] * mean(volumes[-20:]), "range_fraction": (highs[-1] - lows[-1]) / closes[-1],
            "regime": "BENCHMARK_UP" if market > 0 else "BENCHMARK_NONPOSITIVE",
            "strategy_flags": flags}
