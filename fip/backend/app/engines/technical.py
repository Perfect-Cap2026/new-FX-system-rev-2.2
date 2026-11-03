"""Module 5 — Technical analysis: multi-timeframe trend/momentum + levels + trade setup."""
import numpy as np
import pandas as pd

from app.engines import indicators as ind
from app.engines.common import ModuleResult, Signal, finish, py, unavailable

TF_WEIGHTS = {"1wk": 0.30, "1d": 0.45, "1h": 0.25}


def timeframe_view(df: pd.DataFrame) -> dict:
    c = df["close"]
    e20, e50, e200 = ind.ema(c, 20), ind.ema(c, 50), ind.ema(c, 200)
    r = ind.rsi(c)
    m = ind.macd(c)
    a = ind.atr(df)
    x = ind.adx(df)
    last = float(c.iloc[-1])

    # Trend stack: each condition ±1, max |4|
    stack = (np.sign(last - e20.iloc[-1]) + np.sign(e20.iloc[-1] - e50.iloc[-1])
             + np.sign(e50.iloc[-1] - e200.iloc[-1]) + np.sign(e50.iloc[-1] - e50.iloc[-6]))
    trend = float(stack) / 4 * 50  # −50..50

    rsi_v = float(r.iloc[-1])
    mom = np.clip((rsi_v - 50) * 1.2, -24, 24)
    if rsi_v > 72 or rsi_v < 28:  # stretched: momentum counts half, mean-reversion risk
        mom *= 0.5

    hist = m["hist"]
    macd_s = 13 * np.sign(hist.iloc[-1]) + 13 * np.sign(hist.iloc[-1] - hist.iloc[-3])

    adx_v = float(x.iloc[-1])
    strength = 0.7 + 0.6 * min(adx_v, 40) / 40  # 0.7..1.3: weak trends are discounted
    score = float(np.clip((trend + mom + macd_s) * strength, -100, 100))

    if stack >= 3:
        structure = "uptrend"
    elif stack <= -3:
        structure = "downtrend"
    else:
        structure = "range/transition"

    return {
        "score": round(score, 1),
        "structure": structure,
        "close": last,
        "ema20": py(e20.iloc[-1]), "ema50": py(e50.iloc[-1]), "ema200": py(e200.iloc[-1]),
        "rsi": round(rsi_v, 1),
        "macd": py(m["macd"].iloc[-1]), "macd_signal": py(m["signal"].iloc[-1]), "macd_hist": py(hist.iloc[-1]),
        "atr": py(a.iloc[-1]), "adx": round(adx_v, 1),
        "components": {"trend": round(trend, 1), "momentum": round(float(mom), 1), "macd": round(float(macd_s), 1)},
    }


def trade_setup(df: pd.DataFrame, direction: int, levels: list[dict], fib: dict, vp: dict, atr_v: float,
                swing_lows: list[float], swing_highs: list[float]) -> dict | None:
    if direction == 0 or atr_v <= 0:
        return None
    price = float(df["close"].iloc[-1])
    cands = [lv["price"] for lv in levels] + list(fib.get("levels", {}).values())
    if vp:
        cands += [vp["poc"], vp["val"], vp["vah"]]
    if direction > 0:
        pull = [p for p in cands if price - 1.5 * atr_v <= p < price]
        entry = max(pull) if pull else price
        structural = [s for s in swing_lows if s < entry - 0.25 * atr_v]
        stop = (max(structural) - 0.5 * atr_v) if structural else entry - 1.5 * atr_v
        stop = max(stop, entry - 3 * atr_v)
        risk = entry - stop
        res = sorted(lv["price"] for lv in levels if lv["price"] > entry + 0.5 * risk)
        t1 = res[0] if res else entry + 2 * risk
    else:
        pull = [p for p in cands if price < p <= price + 1.5 * atr_v]
        entry = min(pull) if pull else price
        structural = [s for s in swing_highs if s > entry + 0.25 * atr_v]
        stop = (min(structural) + 0.5 * atr_v) if structural else entry + 1.5 * atr_v
        stop = min(stop, entry + 3 * atr_v)
        risk = stop - entry
        sup = sorted((lv["price"] for lv in levels if lv["price"] < entry - 0.5 * risk), reverse=True)
        t1 = sup[0] if sup else entry - 2 * risk
    if risk <= 0:
        return None
    # Structural target plus 2R / 3R, ordered nearest-first so T1 is always the first to be hit
    raw = {round(t1, 6), round(entry + direction * 2 * risk, 6), round(entry + direction * 3 * risk, 6)}
    t1, t2, t3 = (sorted(raw, key=lambda t: abs(t - entry)) + [entry + direction * 4 * risk] * 2)[:3]
    return {
        "direction": "long" if direction > 0 else "short",
        "entry": round(entry, 6), "stop": round(stop, 6),
        "targets": [round(t1, 6), round(t2, 6), round(t3, 6)],
        "risk_per_unit": round(risk, 6),
        "rr": [round(abs(t - entry) / risk, 2) for t in (t1, t2, t3)],
        "entry_type": "limit (pullback to confluence)" if entry != price else "market",
        "stop_basis": "beyond swing structure ± 0.5 ATR" if (swing_lows or swing_highs) else "1.5 ATR",
    }


def analyze(frames: dict[str, pd.DataFrame]) -> ModuleResult:
    views = {tf: timeframe_view(df) for tf, df in frames.items() if df is not None and len(df) >= 60}
    if "1d" not in views:
        return unavailable("technical", "insufficient daily history")

    wsum = sum(TF_WEIGHTS[tf] for tf in views)
    signals = [
        Signal(name=f"{tf} trend/momentum", value=v["structure"], impact=round(v["score"] * TF_WEIGHTS[tf] / wsum, 1),
               note=f"RSI {v['rsi']}, ADX {v['adx']}, MACD hist {'+' if (v['macd_hist'] or 0) > 0 else '−'}")
        for tf, v in views.items()
    ]

    daily = frames["1d"]
    d = views["1d"]
    atr_v = d["atr"] or 0
    levels = ind.support_resistance(daily.tail(250), atr_v)
    fib = ind.fibonacci(daily)
    vp = ind.volume_profile(daily.tail(120)) if daily["volume"].sum() > 0 else {}
    vw = ind.vwap(daily, anchor_bars=20)
    sh, sl = ind.pivots(daily.tail(120), 3, 3)
    recent = daily.tail(120)
    swing_highs = recent["high"][sh].tail(5).tolist()
    swing_lows = recent["low"][sl].tail(5).tolist()

    # Alignment bonus/penalty: higher timeframes agreeing matters
    signs = [np.sign(v["score"]) for v in views.values() if abs(v["score"]) >= 10]
    if len(signs) >= 2 and len(set(signs)) == 1:
        signals.append(Signal(name="MTF alignment", value="aligned", impact=10 * signs[0],
                              note="all timeframes agree"))
    elif len(set(signs)) > 1:
        signals.append(Signal(name="MTF alignment", value="conflict", impact=0, note="timeframes disagree"))

    score_dir = sum(s.impact for s in signals)
    direction = int(np.sign(score_dir)) if abs(score_dir) >= 15 else 0
    setup = trade_setup(daily, direction, levels, fib, vp, atr_v, swing_lows, swing_highs)

    tail = daily.tail(150)
    details = {
        "timeframes": views,
        "levels": levels,
        "fibonacci": fib,
        "volume_profile": {k: v for k, v in vp.items() if k != "profile"} | {"profile": vp.get("profile", [])[::2]} if vp else {},
        "vwap_20d": py(vw.iloc[-1]),
        "setup": setup,
        "series": [{"t": ts.strftime("%Y-%m-%d"), "c": round(float(c), 6)} for ts, c in tail["close"].items()],
    }
    coverage = len(views) / 3
    return finish("technical", signals, coverage=0.6 + 0.4 * coverage, details=details)
