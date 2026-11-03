"""Vectorised indicator library (pandas). All functions take/return pandas objects."""
import numpy as np
import pandas as pd


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(100)


def macd(close: pd.Series, fast=12, slow=26, sig=9) -> pd.DataFrame:
    line = ema(close, fast) - ema(close, slow)
    signal = ema(line, sig)
    return pd.DataFrame({"macd": line, "signal": signal, "hist": line - signal})


def true_range(df: pd.DataFrame) -> pd.Series:
    pc = df["close"].shift()
    return pd.concat([df["high"] - df["low"], (df["high"] - pc).abs(), (df["low"] - pc).abs()], axis=1).max(axis=1)


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    return true_range(df).ewm(alpha=1 / n, adjust=False).mean()


def adx(df: pd.DataFrame, n: int = 14) -> pd.Series:
    up = df["high"].diff()
    dn = -df["low"].diff()
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = atr(df, n)
    pdi = 100 * pd.Series(plus_dm, index=df.index).ewm(alpha=1 / n, adjust=False).mean() / tr
    mdi = 100 * pd.Series(minus_dm, index=df.index).ewm(alpha=1 / n, adjust=False).mean() / tr
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return dx.ewm(alpha=1 / n, adjust=False).mean().fillna(0)


def vwap(df: pd.DataFrame, anchor_bars: int | None = None) -> pd.Series:
    d = df if anchor_bars is None else df.tail(anchor_bars)
    tp = (d["high"] + d["low"] + d["close"]) / 3
    v = d["volume"].replace(0, np.nan).fillna(1)
    return (tp * v).cumsum() / v.cumsum()


def obv(df: pd.DataFrame) -> pd.Series:
    return (np.sign(df["close"].diff().fillna(0)) * df["volume"]).cumsum()


def chaikin_ad(df: pd.DataFrame) -> pd.Series:
    rng = (df["high"] - df["low"]).replace(0, np.nan)
    mfm = ((df["close"] - df["low"]) - (df["high"] - df["close"])) / rng
    return (mfm.fillna(0) * df["volume"]).cumsum()


def volume_profile(df: pd.DataFrame, bins: int = 40, value_area: float = 0.7) -> dict:
    lo, hi = df["low"].min(), df["high"].max()
    if not np.isfinite(lo) or hi <= lo:
        return {}
    edges = np.linspace(lo, hi, bins + 1)
    tp = ((df["high"] + df["low"] + df["close"]) / 3).values
    vol = df["volume"].replace(0, 1).fillna(1).values
    hist, _ = np.histogram(tp, bins=edges, weights=vol)
    mids = (edges[:-1] + edges[1:]) / 2
    poc_i = int(hist.argmax())
    # expand value area outward from POC
    lo_i = hi_i = poc_i
    total, acc = hist.sum(), hist[poc_i]
    while acc < value_area * total and (lo_i > 0 or hi_i < bins - 1):
        nxt_lo = hist[lo_i - 1] if lo_i > 0 else -1
        nxt_hi = hist[hi_i + 1] if hi_i < bins - 1 else -1
        if nxt_hi >= nxt_lo:
            hi_i += 1
            acc += hist[hi_i]
        else:
            lo_i -= 1
            acc += hist[lo_i]
    return {"poc": float(mids[poc_i]), "val": float(edges[lo_i]), "vah": float(edges[hi_i + 1]),
            "profile": [{"price": float(m), "volume": float(h)} for m, h in zip(mids, hist)]}


def pivots(df: pd.DataFrame, left: int = 3, right: int = 3) -> tuple[pd.Series, pd.Series]:
    """Fractal swing highs/lows. Returns boolean masks (confirmed only — no look-ahead past `right`)."""
    h, l = df["high"], df["low"]
    w = left + right + 1
    sh = h == h.rolling(w, center=True).max()
    sl = l == l.rolling(w, center=True).min()
    return sh.fillna(False), sl.fillna(False)


def support_resistance(df: pd.DataFrame, atr_val: float, max_levels: int = 6) -> list[dict]:
    """Cluster pivot prices within 0.5 ATR; strength = touches."""
    sh, sl = pivots(df, 5, 5)
    prices = pd.concat([df["high"][sh], df["low"][sl]]).sort_values().values
    if len(prices) == 0 or atr_val <= 0:
        return []
    clusters: list[list[float]] = [[prices[0]]]
    for p in prices[1:]:
        if p - clusters[-1][-1] <= 0.5 * atr_val:
            clusters[-1].append(p)
        else:
            clusters.append([p])
    levels = [{"price": float(np.mean(c)), "touches": len(c)} for c in clusters]
    last = float(df["close"].iloc[-1])
    levels.sort(key=lambda x: (-x["touches"], abs(x["price"] - last)))
    out = levels[:max_levels]
    for lv in out:
        lv["type"] = "resistance" if lv["price"] > last else "support"
    return sorted(out, key=lambda x: x["price"])


def fibonacci(df: pd.DataFrame, lookback: int = 120) -> dict:
    d = df.tail(lookback)
    hi_i, lo_i = d["high"].idxmax(), d["low"].idxmin()
    hi, lo = float(d["high"].max()), float(d["low"].min())
    up_leg = lo_i < hi_i  # swing low came first → retrace an up-move
    ratios = [0.236, 0.382, 0.5, 0.618, 0.786]
    levels = {str(r): (hi - (hi - lo) * r) if up_leg else (lo + (hi - lo) * r) for r in ratios}
    return {"swing_high": hi, "swing_low": lo, "direction": "up" if up_leg else "down", "levels": levels}
