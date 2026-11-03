"""Module 7 — Intermarket: correlations, lead/lag, drivers, risk regime, implied direction."""
import numpy as np
import pandas as pd

from app.engines.common import ModuleResult, Signal, finish, unavailable
from app.providers.base import LEVEL_SERIES


def returns_frame(closes: dict[str, pd.Series], symbols: dict[str, str]) -> pd.DataFrame:
    cols = {}
    for name, s in closes.items():
        if s is None or len(s) < 30:
            continue
        s = s.copy()
        s.index = pd.to_datetime(s.index).tz_convert(None).normalize() if s.index.tz is not None else pd.to_datetime(s.index).normalize()
        s = s[~s.index.duplicated(keep="last")]
        cols[name] = s.diff() if symbols.get(name) in LEVEL_SERIES else s.pct_change()
    df = pd.DataFrame(cols)
    df = df[df.index.dayofweek < 5]  # align crypto to the trading-day calendar
    return df.dropna(how="all").ffill(limit=1).dropna()


def lead_lag(r: pd.DataFrame, target: str, max_lag: int = 5, window: int = 120) -> list[dict]:
    d = r.tail(window)
    out = []
    for c in d.columns:
        if c == target:
            continue
        best = (0, 0.0)
        for lag in range(-max_lag, max_lag + 1):
            rho = d[target].corr(d[c].shift(lag))
            if pd.notna(rho) and abs(rho) > abs(best[1]):
                best = (lag, float(rho))
        out.append({"asset": c, "best_lag": best[0], "rho": round(best[1], 3),
                    "reading": (f"{c} leads by {best[0]}d" if best[0] > 0 else f"{c} lags by {-best[0]}d" if best[0] < 0
                                else "contemporaneous")})
    return sorted(out, key=lambda x: -abs(x["rho"]))


def regime(closes: dict[str, pd.Series]) -> dict:
    pts, notes = 0, []
    vix = closes.get("VIX")
    if vix is not None and len(vix) > 20:
        v = float(vix.iloc[-1])
        pts += 1 if v < 17 else -1 if v > 22 else 0
        pts += 1 if v < vix.tail(20).mean() else -1
        notes.append(f"VIX {v:.1f}")
    spx = closes.get("S&P 500")
    if spx is not None and len(spx) > 200:
        above = spx.iloc[-1] > spx.tail(200).mean()
        pts += 1 if above else -1
        notes.append(f"S&P {'above' if above else 'below'} 200d")
    dxy = closes.get("DXY")
    if dxy is not None and len(dxy) > 20:
        up = dxy.iloc[-1] > dxy.tail(20).mean()
        pts += -1 if up else 1
        notes.append(f"DXY {'rising' if up else 'falling'}")
    label = "Risk-on" if pts >= 2 else "Risk-off" if pts <= -2 else "Mixed"
    return {"label": label, "points": pts, "notes": notes}


def analyze(target_name: str, target_close: pd.Series, basket: dict[str, pd.Series], symbols: dict[str, str],
            window: int = 60) -> tuple[ModuleResult, dict]:
    closes = dict(basket)
    closes.setdefault(target_name, target_close)
    r = returns_frame(closes, symbols)
    if target_name not in r or len(r) < window:
        return unavailable("intermarket", "insufficient overlapping history"), {}
    w = r.tail(window)
    corr = w.corr()

    # PCA on the correlation matrix → common factor
    vals, vecs = np.linalg.eigh(corr.values)
    pc1 = vecs[:, -1] * np.sign(vecs[:, -1].sum() or 1)
    explained = float(vals[-1] / vals.sum())

    drivers = []
    for c in w.columns:
        if c == target_name:
            continue
        rho = corr.loc[target_name, c]
        if pd.notna(rho):
            drivers.append({"asset": c, "rho": round(float(rho), 3), "r2": round(float(rho ** 2), 3)})
    drivers.sort(key=lambda x: -x["r2"])

    # Implied direction: what strongly-correlated markets have done over 20 bars
    sig = []
    implied = 0.0
    for d in drivers[:4]:
        if abs(d["rho"]) < 0.25:
            continue
        s20 = r[d["asset"]].tail(20)
        z = float(s20.sum() / ((r[d["asset"]].tail(250).std() or 1) * np.sqrt(20)))
        contrib = float(np.clip(d["rho"] * z * 18, -15, 15))
        implied += contrib
        sig.append(Signal(name=f"{d['asset']} (ρ={d['rho']:+.2f})", value=f"20d move z={z:+.2f}", impact=round(contrib, 1),
                          note="correlated market's recent trend"))
    reg = regime(closes)
    if reg["label"] != "Mixed":
        # Risk regime matters for assets that are positively correlated with equities
        eq_rho = corr.loc[target_name].get("S&P 500", 0) if "S&P 500" in corr else 0
        if target_name != "S&P 500" and pd.notna(eq_rho) and abs(eq_rho) > 0.2:
            imp = (10 if reg["label"] == "Risk-on" else -10) * np.sign(eq_rho)
            sig.append(Signal(name="Risk regime", value=reg["label"], impact=float(imp), note=", ".join(reg["notes"])))
    if not sig:
        sig.append(Signal(name="Correlations", value="weak", impact=0, note="no strong intermarket driver in last 60d"))

    matrix = {"assets": list(corr.columns),
              "values": [[round(float(x), 3) if pd.notna(x) else None for x in row] for row in corr.values]}
    extra = {"correlation_matrix": matrix, "lead_lag": lead_lag(r, target_name), "drivers": drivers[:6],
             "pc1": {"explained": round(explained, 3), "loadings": dict(zip(corr.columns, np.round(pc1, 3).tolist()))},
             "regime": reg, "window": window}
    return finish("intermarket", sig, coverage=0.8, details=extra, cap=60), extra
