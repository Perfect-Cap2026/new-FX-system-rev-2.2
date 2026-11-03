"""Module 2 — Microeconomic / sector engine: relative strength, rankings, rotation phase."""
import numpy as np
import pandas as pd

from app.providers.base import SECTORS

CYCLE = {
    "Early cycle": ["XLY", "XLF", "XLI", "XLRE"],
    "Mid cycle": ["XLK", "XLC", "XLB"],
    "Late cycle": ["XLE", "XLB", "XLI"],
    "Defensive / recession": ["XLU", "XLP", "XLV"],
}


def analyze(closes: dict[str, pd.Series], bench: pd.Series) -> dict:
    rows = []
    for sym, s in closes.items():
        if s is None or len(s) < 130 or bench is None or len(bench) < 130:
            continue
        row = {"symbol": sym, "sector": SECTORS.get(sym, sym)}
        for label, n in (("1m", 21), ("3m", 63), ("6m", 126)):
            row[f"ret_{label}"] = float(s.iloc[-1] / s.iloc[-1 - n] - 1)
            row[f"rs_{label}"] = row[f"ret_{label}"] - float(bench.iloc[-1] / bench.iloc[-1 - n] - 1)
        row["above_50d"] = bool(s.iloc[-1] > s.tail(50).mean())
        row["score"] = 0.5 * row["rs_1m"] + 0.3 * row["rs_3m"] + 0.2 * row["rs_6m"]
        # Acceleration: short-term RS improving vs long-term → rotating in
        row["momentum_shift"] = "rotating in" if row["rs_1m"] > row["rs_3m"] / 3 + 0.005 else \
            "rotating out" if row["rs_1m"] < row["rs_3m"] / 3 - 0.005 else "steady"
        rows.append(row)
    if not rows:
        return {"rankings": [], "phase": None}
    rows.sort(key=lambda r: -r["score"])
    for i, r in enumerate(rows, 1):
        r["rank"] = i
        r["outlook"] = "Overweight" if i <= 3 else "Underweight" if i > len(rows) - 3 else "Neutral"
        for k in list(r):
            if isinstance(r[k], float):
                r[k] = round(r[k], 4)
    rank = {r["symbol"]: r["rank"] for r in rows}
    phase_scores = {p: float(np.mean([rank[s] for s in syms if s in rank])) for p, syms in CYCLE.items()
                    if any(s in rank for s in syms)}
    phase = min(phase_scores, key=phase_scores.get) if phase_scores else None
    return {"rankings": rows, "phase": phase,
            "phase_scores": {k: round(v, 2) for k, v in phase_scores.items()},
            "note": "Phase = cycle group whose sectors have the best average relative-strength rank (lower = stronger)."}
