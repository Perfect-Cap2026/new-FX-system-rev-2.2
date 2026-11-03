"""Module 4 — Institutional / Smart Money Concepts from OHLCV.

These are price *signatures* associated with institutional activity, inferred from bars.
True order flow needs tick/L2 data; see docs/ARCHITECTURE.md §4.4.
"""
import numpy as np
import pandas as pd

from app.engines import indicators as ind
from app.engines.common import ModuleResult, Signal, finish, unavailable


def swings(df: pd.DataFrame, k: int = 3) -> list[dict]:
    sh, sl = ind.pivots(df, k, k)
    out = []
    for i, ts in enumerate(df.index):
        if sh.iloc[i]:
            out.append({"i": i, "t": ts, "type": "H", "price": float(df["high"].iloc[i])})
        if sl.iloc[i]:
            out.append({"i": i, "t": ts, "type": "L", "price": float(df["low"].iloc[i])})
    return out


def structure_events(df: pd.DataFrame, sw: list[dict], k: int = 3) -> tuple[list[dict], np.ndarray]:
    """Walk bars; a close beyond the latest confirmed swing = BOS (with trend) or CHoCH (against).
    Returns events and a per-bar state array (+1 bullish, −1 bearish, 0 unknown)."""
    close = df["close"].values
    state = np.zeros(len(df))
    events: list[dict] = []
    trend = 0
    last_h = last_l = None
    broken_h = broken_l = None
    by_confirm: dict[int, list[dict]] = {}
    for s in sw:  # a pivot is only known k bars later
        by_confirm.setdefault(s["i"] + k, []).append(s)
    for i in range(len(df)):
        for s in by_confirm.get(i, []):
            if s["type"] == "H":
                last_h = s
            else:
                last_l = s
        if last_h and last_h is not broken_h and close[i] > last_h["price"]:
            kind = "BOS" if trend >= 0 else "CHoCH"
            events.append({"i": i, "t": df.index[i], "kind": kind, "dir": "bullish", "level": last_h["price"]})
            trend, broken_h = 1, last_h
        elif last_l and last_l is not broken_l and close[i] < last_l["price"]:
            kind = "BOS" if trend <= 0 else "CHoCH"
            events.append({"i": i, "t": df.index[i], "kind": kind, "dir": "bearish", "level": last_l["price"]})
            trend, broken_l = -1, last_l
        state[i] = trend
    return events, state


def fair_value_gaps(df: pd.DataFrame, atr_v: float, keep: int = 4) -> list[dict]:
    h, l = df["high"].values, df["low"].values
    gaps = []
    for i in range(2, len(df)):
        if l[i] > h[i - 2] and l[i] - h[i - 2] >= 0.1 * atr_v:
            gaps.append({"i": i, "dir": "bullish", "bottom": float(h[i - 2]), "top": float(l[i])})
        elif h[i] < l[i - 2] and l[i - 2] - h[i] >= 0.1 * atr_v:
            gaps.append({"i": i, "dir": "bearish", "bottom": float(h[i]), "top": float(l[i - 2])})
    open_gaps = []
    for g in gaps:
        after = df.iloc[g["i"] + 1:]
        filled = (after["low"] <= g["bottom"]).any() if g["dir"] == "bullish" else (after["high"] >= g["top"]).any()
        if not filled:
            g["t"] = df.index[g["i"]].strftime("%Y-%m-%d")
            open_gaps.append(g)
    return open_gaps[-keep:]


def order_blocks(df: pd.DataFrame, events: list[dict], keep: int = 4) -> list[dict]:
    o, c = df["open"].values, df["close"].values
    obs = []
    for ev in events[-12:]:
        bull = ev["dir"] == "bullish"
        for j in range(ev["i"] - 1, max(ev["i"] - 12, 0), -1):
            if (bull and c[j] < o[j]) or (not bull and c[j] > o[j]):
                lo, hi = float(df["low"].iloc[j]), float(df["high"].iloc[j])
                after = df["close"].iloc[ev["i"] + 1:]
                broken = (after < lo).any() if bull else (after > hi).any()
                if not broken:
                    obs.append({"t": df.index[j].strftime("%Y-%m-%d"), "dir": ev["dir"], "low": lo, "high": hi,
                                "from": ev["kind"]})
                break
    return obs[-keep:]


def liquidity_pools(df: pd.DataFrame, sw: list[dict], atr_v: float) -> dict:
    last = float(df["close"].iloc[-1])
    highs = [s for s in sw[-30:] if s["type"] == "H"]
    lows = [s for s in sw[-30:] if s["type"] == "L"]

    def equal(levels, side):
        pools = []
        for a in range(len(levels)):
            for b in range(a + 1, len(levels)):
                if abs(levels[a]["price"] - levels[b]["price"]) <= 0.15 * atr_v:
                    lvl = max(levels[a]["price"], levels[b]["price"]) if side == "buy" else min(levels[a]["price"], levels[b]["price"])
                    after = df.iloc[levels[b]["i"] + 1:]
                    swept = (after["high"] > lvl).any() if side == "buy" else (after["low"] < lvl).any()
                    if not swept:
                        pools.append(round(lvl, 6))
        return sorted(set(pools))

    unswept_h = [s["price"] for s in highs if not (df["high"].iloc[s["i"] + 1:] > s["price"]).any()]
    unswept_l = [s["price"] for s in lows if not (df["low"].iloc[s["i"] + 1:] < s["price"]).any()]
    return {
        "buy_side": {"equal_highs": equal(highs, "buy"), "nearest_swing_high": min([p for p in unswept_h if p > last], default=None)},
        "sell_side": {"equal_lows": equal(lows, "sell"), "nearest_swing_low": max([p for p in unswept_l if p < last], default=None)},
    }


def sweeps(df: pd.DataFrame, sw: list[dict], lookback: int = 10) -> list[dict]:
    out = []
    n = len(df)
    for i in range(max(n - lookback, 0), n):
        prior = [s for s in sw if s["i"] < i - 2 and s["i"] > i - 60]
        hi, lo, cl = df["high"].iloc[i], df["low"].iloc[i], df["close"].iloc[i]
        for s in prior:
            if s["type"] == "H" and hi > s["price"] > cl:
                out.append({"t": df.index[i].strftime("%Y-%m-%d"), "dir": "bearish", "level": s["price"],
                            "note": "swept buy-side liquidity, closed back below"})
                break
            if s["type"] == "L" and lo < s["price"] < cl:
                out.append({"t": df.index[i].strftime("%Y-%m-%d"), "dir": "bullish", "level": s["price"],
                            "note": "swept sell-side liquidity, closed back above"})
                break
    return out[-3:]


def _slope(s: pd.Series) -> float:
    y = s.values.astype(float)
    if len(y) < 3 or np.allclose(y.std(), 0):
        return 0.0
    x = np.arange(len(y))
    return float(np.polyfit(x, (y - y.mean()) / y.std(), 1)[0])


def probability_matrix(df: pd.DataFrame, state: np.ndarray, horizon: int = 10) -> dict:
    fwd = df["close"].shift(-horizon) / df["close"] - 1
    frame = pd.DataFrame({"state": state, "fwd": fwd}).dropna()
    frame = frame[frame["state"] != 0]
    if len(frame) < 50:
        return {}
    base = float((frame["fwd"] > 0).mean())
    out = {"horizon_bars": horizon, "base_rate_up": round(base, 3), "samples": int(len(frame))}
    for st, name in ((1, "bullish_structure"), (-1, "bearish_structure")):
        sub = frame[frame["state"] == st]
        if len(sub) >= 20:
            out[name] = {"p_up": round(float((sub["fwd"] > 0).mean()), 3),
                         "avg_return": round(float(sub["fwd"].mean()), 5), "n": int(len(sub))}
    return out


def analyze(df: pd.DataFrame) -> ModuleResult:
    if df is None or len(df) < 120:
        return unavailable("institutional", "insufficient history")
    df = df.tail(500)
    atr_v = float(ind.atr(df).iloc[-1])
    last = float(df["close"].iloc[-1])
    sw = swings(df)
    events, state = structure_events(df, sw)
    signals: list[Signal] = []

    cur = int(state[-1])
    last_ev = events[-1] if events else None
    if last_ev:
        fresh = len(df) - 1 - last_ev["i"] <= 15
        base = 22 if last_ev["kind"] == "BOS" else 18
        imp = base * (1 if last_ev["dir"] == "bullish" else -1) * (1.0 if fresh else 0.7)
        signals.append(Signal(name="Market structure", value=f"{last_ev['kind']} {last_ev['dir']}", impact=round(imp, 1),
                              note=f"broke {last_ev['level']:.5g} on {last_ev['t']:%Y-%m-%d}"))

    hs = [s["price"] for s in sw if s["type"] == "H"][-2:]
    ls = [s["price"] for s in sw if s["type"] == "L"][-2:]
    if len(hs) == 2 and len(ls) == 2:
        hh, hl = hs[1] > hs[0], ls[1] > ls[0]
        pattern = f"{'HH' if hh else 'LH'}/{'HL' if hl else 'LL'}"
        imp = 15 if (hh and hl) else -15 if (not hh and not hl) else 0
        signals.append(Signal(name="Swing sequence", value=pattern, impact=imp))

    sw_events = sweeps(df, sw)
    if sw_events:
        e = sw_events[-1]
        signals.append(Signal(name="Liquidity sweep / stop hunt", value=e["dir"],
                              impact=14 if e["dir"] == "bullish" else -14, note=f"{e['note']} ({e['t']})"))

    fvgs = fair_value_gaps(df, atr_v)
    obs = order_blocks(df, events)
    near_bull = [z for z in fvgs + obs if z["dir"] == "bullish" and last - 2 * atr_v <= z.get("top", z.get("high")) <= last + 0.2 * atr_v]
    near_bear = [z for z in fvgs + obs if z["dir"] == "bearish" and last - 0.2 * atr_v <= z.get("bottom", z.get("low")) <= last + 2 * atr_v]
    if near_bull or near_bear:
        imp = 7 * min(len(near_bull), 2) - 7 * min(len(near_bear), 2)
        signals.append(Signal(name="Nearby imbalances (FVG/OB)", value=f"{len(near_bull)} bull / {len(near_bear)} bear",
                              impact=imp, note="unmitigated zones within 2 ATR act as reaction areas"))

    hi60, lo60 = float(df["high"].tail(60).max()), float(df["low"].tail(60).min())
    pos = (last - lo60) / (hi60 - lo60) if hi60 > lo60 else 0.5
    zone = "premium" if pos > 0.62 else "discount" if pos < 0.38 else "equilibrium"
    pd_imp = 0.0
    if cur > 0:
        pd_imp = 8 if zone == "discount" else -6 if zone == "premium" else 0
    elif cur < 0:
        pd_imp = -8 if zone == "premium" else 6 if zone == "discount" else 0
    signals.append(Signal(name="Premium / discount", value=f"{zone} ({pos:.0%} of 60-bar range)", impact=pd_imp,
                          note="buy in discount, sell in premium"))

    accdist = "n/a (no volume)"
    if df["volume"].tail(40).sum() > 0:
        ad_s = _slope(ind.chaikin_ad(df).tail(30))
        px_s = _slope(df["close"].tail(30))
        diff = ad_s - px_s
        if abs(diff) > 0.03:
            accdist = "accumulation" if diff > 0 else "distribution"
            signals.append(Signal(name="Accumulation / distribution", value=accdist,
                                  impact=12 if diff > 0 else -12, note="Chaikin A/D slope vs price slope (30 bars)"))
        else:
            accdist = "neutral"

    probs = probability_matrix(df, state)
    key = "bullish_structure" if cur > 0 else "bearish_structure" if cur < 0 else None
    if key and key in probs:
        edge = probs[key]["p_up"] - probs["base_rate_up"]
        signals.append(Signal(name="Historical edge", value=f"P(up {probs['horizon_bars']} bars)={probs[key]['p_up']:.0%}",
                              impact=round(float(np.clip(edge * 100, -10, 10)), 1),
                              note=f"vs base rate {probs['base_rate_up']:.0%}, n={probs[key]['n']}"))

    details = {
        "structure_state": "bullish" if cur > 0 else "bearish" if cur < 0 else "undefined",
        "events": [{"t": e["t"].strftime("%Y-%m-%d"), "kind": e["kind"], "dir": e["dir"], "level": e["level"]} for e in events[-6:]],
        "fair_value_gaps": fvgs, "order_blocks": obs,
        "liquidity": liquidity_pools(df, sw, atr_v), "sweeps": sw_events,
        "premium_discount": {"zone": zone, "position": round(pos, 3), "range_high": hi60, "range_low": lo60},
        "accumulation_distribution": accdist,
        "probability_matrix": probs,
    }
    return finish("institutional", signals, coverage=0.85, details=details)
