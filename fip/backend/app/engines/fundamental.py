"""Module 3 — Fundamental analysis (stocks, FX, commodities, indices) + bull/base/bear scenarios."""
import numpy as np
import pandas as pd

from app.engines.common import ModuleResult, Signal, finish, unavailable
from app.providers.base import asset_class, fx_currencies


def _c(x, lo, hi):
    return round(float(np.clip(x, lo, hi)), 1)


def stock_signals(f: dict) -> list[Signal]:
    s = []
    if (g := f.get("revenueGrowth")) is not None:
        s.append(Signal(name="Revenue growth", value=f"{g:.1%}", impact=_c((g - 0.05) * 100, -12, 12)))
    if (g := f.get("earningsGrowth")) is not None:
        s.append(Signal(name="EPS growth", value=f"{g:.1%}", impact=_c((g - 0.05) * 60, -12, 12)))
    if (m := f.get("operatingMargins")) is not None:
        s.append(Signal(name="Operating margin", value=f"{m:.1%}", impact=_c((m - 0.12) * 60, -8, 8)))
    if (r := f.get("returnOnEquity")) is not None:
        s.append(Signal(name="ROE", value=f"{r:.1%}", impact=_c((r - 0.12) * 60, -10, 10),
                        note="ROIC needs invested-capital data (target: filings provider)"))
    if (d := f.get("debtToEquity")) is not None:
        s.append(Signal(name="Debt / equity", value=f"{d / 100:.2f}x", impact=_c((100 - d) / 12, -8, 8)))
    fcf, mc = f.get("freeCashflow"), f.get("marketCap")
    if fcf is not None and mc:
        y = fcf / mc
        s.append(Signal(name="FCF yield", value=f"{y:.1%}", impact=_c((y - 0.03) * 300, -10, 10)))
    if (pe := f.get("forwardPE")) is not None and pe > 0:
        s.append(Signal(name="Forward P/E", value=round(pe, 1), impact=_c((22 - pe) / 2, -10, 8)))
    if (peg := f.get("pegRatio")) is not None and peg > 0:
        s.append(Signal(name="PEG", value=round(peg, 2), impact=_c((1.5 - peg) * 8, -8, 8)))
    if (ev := f.get("enterpriseToEbitda")) is not None and ev > 0:
        s.append(Signal(name="EV / EBITDA", value=round(ev, 1), impact=_c((14 - ev) / 1.5, -8, 6)))
    return s


def seasonality(df: pd.DataFrame, month: int) -> dict | None:
    if df is None or len(df) < 500:
        return None
    m = df["close"].resample("ME").last().pct_change().dropna()
    same = m[m.index.month == month]
    if len(same) < 4:
        return None
    return {"month": month, "avg_return": float(same.mean()), "hit_rate": float((same > 0).mean()), "years": int(len(same))}


def valuation_vs_history(df: pd.DataFrame) -> float | None:
    """z-score of price vs its 3-year mean — a crude PPP / mean-reversion proxy for FX and commodities."""
    if df is None or len(df) < 600:
        return None
    c = df["close"].tail(756)
    return float((c.iloc[-1] - c.mean()) / (c.std() or 1))


def scenarios(price: float, daily: pd.DataFrame, score: float, signals: list[Signal]) -> dict:
    vol_m = float(daily["close"].pct_change().tail(120).std() * np.sqrt(21))
    tilt = score / 100
    pos = [s.name for s in sorted(signals, key=lambda x: -x.impact) if s.impact > 0][:3]
    neg = [s.name for s in sorted(signals, key=lambda x: x.impact) if s.impact < 0][:3]
    p_bull = float(np.clip(0.25 + tilt * 0.25, 0.1, 0.5))
    p_bear = float(np.clip(0.25 - tilt * 0.25, 0.1, 0.5))
    return {
        "horizon": "1 month",
        "monthly_volatility": round(vol_m, 4),
        "bull": {"target": round(price * (1 + 1.2 * vol_m), 6), "probability": round(p_bull, 2),
                 "drivers": pos or ["broad risk-on / momentum continuation"]},
        "base": {"target": round(price * (1 + tilt * 0.5 * vol_m), 6), "probability": round(1 - p_bull - p_bear, 2),
                 "drivers": ["current signals persist"]},
        "bear": {"target": round(price * (1 - 1.2 * vol_m), 6), "probability": round(p_bear, 2),
                 "drivers": neg or ["risk-off shock / mean reversion"]},
        "note": "Targets are ±1.2σ monthly moves; probabilities are tilted by the composite fundamental score, not calibrated.",
    }


def analyze(symbol: str, fund: dict, daily: pd.DataFrame, weekly: pd.DataFrame | None, snap: dict | None,
            month: int) -> ModuleResult:
    ac = asset_class(symbol)
    sig: list[Signal] = []
    details: dict = {"asset_class": ac}
    long_df = weekly if weekly is not None and len(weekly) > 150 else daily

    if ac == "stock":
        sig = stock_signals(fund)
        details["metrics"] = fund
    elif ac == "forex":
        pair = fx_currencies(symbol)
        banks = (snap or {}).get("central_banks", {}).get("banks", {})
        if pair and pair[0] in banks and pair[1] in banks:
            carry = banks[pair[0]]["rate"] - banks[pair[1]]["rate"]
            sig.append(Signal(name="Carry (annual)", value=f"{carry:+.2f}%", impact=_c(carry * 4, -15, 15)))
            ib, iq = banks[pair[0]].get("inflation"), banks[pair[1]].get("inflation")
            if ib is not None and iq is not None:
                sig.append(Signal(name="Inflation divergence", value=f"{ib - iq:+.2f}pp", impact=_c(-(ib - iq) * 5, -10, 10),
                                  note="higher relative inflation erodes purchasing power"))
        z = valuation_vs_history(long_df)
        if z is not None:
            sig.append(Signal(name="Valuation vs 3y mean (PPP proxy)", value=f"z={z:+.2f}", impact=_c(-z * 6, -12, 12)))
        details["note"] = "Trade balance / current account: target-state via IMF & World Bank APIs."
    elif ac == "commodity":
        z = valuation_vs_history(long_df)
        if z is not None:
            sig.append(Signal(name="Price vs 3y mean", value=f"z={z:+.2f}", impact=_c(-z * 5, -10, 10)))
        details["note"] = "Inventories / production: target-state via EIA (energy), WGC (gold), USDA (grains)."
    elif ac == "index":
        pe = fund.get("trailingPE")
        y10 = ((snap or {}).get("rates") or {}).get("10Y yield")
        if pe and y10:
            gap = 100 / pe - y10
            sig.append(Signal(name="Equity risk premium", value=f"{gap:+.2f}pp (EY {100 / pe:.2f}% − 10Y {y10:.2f}%)",
                              impact=_c(gap * 8, -15, 15)))
    elif ac == "crypto":
        return unavailable("fundamental", "no fundamental model for crypto (use on-chain data provider)")

    seas = seasonality(daily if len(daily) > 1000 else long_df, month)
    if seas:
        details["seasonality"] = seas
        sig.append(Signal(name="Seasonality", value=f"{seas['avg_return']:+.2%} avg, {seas['hit_rate']:.0%} up ({seas['years']}y)",
                          impact=_c(seas["avg_return"] * 400 * (abs(seas["hit_rate"] - 0.5) * 2 + 0.3), -8, 8)))

    if not sig:
        return unavailable("fundamental", "no fundamental data returned")
    res = finish("fundamental", sig, coverage=min(1.0, 0.4 + 0.1 * len(sig)), details=details, cap=80)
    res.details["scenarios"] = scenarios(float(daily["close"].iloc[-1]), daily, res.score, sig)
    return res
