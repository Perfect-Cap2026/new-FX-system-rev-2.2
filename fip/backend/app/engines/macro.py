"""Module 1 — Macroeconomic engine (US-centric from FRED + central-bank table for FX)."""
from concurrent.futures import ThreadPoolExecutor
from math import erf, exp, sqrt
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from app.engines.common import ModuleResult, Signal, finish, unavailable
from app.providers.base import asset_class, fx_currencies

SERIES = {
    "CPIAUCSL": "CPI", "PCEPILFE": "Core PCE", "PPIFIS": "PPI final demand", "UNRATE": "Unemployment rate",
    "PAYEMS": "Nonfarm payrolls", "RSAFS": "Retail sales", "INDPRO": "Industrial production",
    "BUSINV": "Business inventories", "PCE": "Consumer spending", "UMCSENT": "Consumer sentiment",
    "DFF": "Fed funds", "DGS10": "10Y yield", "DGS2": "2Y yield", "DGS3MO": "3M yield",
    "T10YIE": "10Y breakeven", "BAMLH0A0HYM2": "HY OAS", "WALCL": "Fed balance sheet",
    "WTREGEN": "Treasury General Account", "RRPONTSYD": "Reverse repo", "SAHMREALTIME": "Sahm rule",
}

CB_FILE = Path(__file__).resolve().parent.parent / "data" / "central_banks.yaml"


def load_central_banks() -> dict:
    with open(CB_FILE) as f:
        return yaml.safe_load(f)


def fetch_all(fetch) -> dict[str, pd.Series]:
    with ThreadPoolExecutor(max_workers=8) as ex:
        return dict(zip(SERIES, ex.map(fetch, SERIES)))


def _yoy(s: pd.Series, periods: int = 12) -> float | None:
    return float(s.iloc[-1] / s.iloc[-1 - periods] - 1) * 100 if len(s) > periods else None


def _ann3m(s: pd.Series) -> float | None:
    return float((s.iloc[-1] / s.iloc[-4]) ** 4 - 1) * 100 if len(s) > 4 else None


def _last(s: pd.Series) -> float | None:
    return float(s.iloc[-1]) if len(s) else None


def _bn(s: pd.Series) -> pd.Series:
    return s / 1000 if len(s) and s.median() > 100_000 else s  # millions → billions


def _phi(x: float) -> float:
    return 0.5 * (1 + erf(x / sqrt(2)))


def snapshot(data: dict[str, pd.Series]) -> dict:
    out: dict = {"indicators": {}, "as_of": {}}
    avail = {k: v for k, v in data.items() if v is not None and len(v) > 0}
    for k, s in avail.items():
        out["as_of"][k] = s.index[-1].strftime("%Y-%m-%d")

    # ---- Inflation
    infl = {}
    for k in ("CPIAUCSL", "PCEPILFE", "PPIFIS"):
        if k in avail:
            infl[SERIES[k]] = {"yoy": _yoy(avail[k]), "ann_3m": _ann3m(avail[k])}
    trend_votes = [v["ann_3m"] - v["yoy"] for v in infl.values() if v["yoy"] is not None and v["ann_3m"] is not None]
    infl_delta = float(np.mean(trend_votes)) if trend_votes else 0.0
    out["inflation"] = {
        "series": infl,
        "direction": "Rising" if infl_delta > 0.3 else "Falling" if infl_delta < -0.3 else "Stable",
        "momentum": round(infl_delta, 2),
    }

    # ---- Growth / labour
    g = {}
    if "PAYEMS" in avail and len(avail["PAYEMS"]) > 4:
        g["payrolls_3m_avg_k"] = float(avail["PAYEMS"].diff().tail(3).mean())
    for k in ("RSAFS", "INDPRO", "PCE", "BUSINV"):
        if k in avail:
            g[f"{SERIES[k]} YoY %"] = _yoy(avail[k])
    if "UNRATE" in avail and len(avail["UNRATE"]) > 4:
        u = avail["UNRATE"]
        g["unemployment"] = float(u.iloc[-1])
        g["unemployment_3m_change"] = float(u.iloc[-1] - u.iloc[-4])
    if "UMCSENT" in avail:
        g["consumer_sentiment"] = _last(avail["UMCSENT"])
    votes = []
    if "payrolls_3m_avg_k" in g:
        votes.append(np.clip((g["payrolls_3m_avg_k"] - 100) / 100, -1, 1))
    for k in ("Retail sales YoY %", "Industrial production YoY %", "Consumer spending YoY %"):
        if g.get(k) is not None:
            votes.append(np.clip((g[k] - 2) / 3, -1, 1))
    if "unemployment_3m_change" in g:
        votes.append(np.clip(-g["unemployment_3m_change"] / 0.3, -1, 1))
    growth = float(np.mean(votes)) if votes else 0.0
    out["growth"] = {"indicators": g, "momentum": round(growth, 2),
                     "label": "Expanding" if growth > 0.2 else "Slowing" if growth < -0.2 else "Steady"}

    # ---- Rates & curve
    rates = {SERIES[k]: _last(avail[k]) for k in ("DFF", "DGS3MO", "DGS2", "DGS10", "T10YIE") if k in avail}
    if "DGS10" in avail and "DGS3MO" in avail:
        rates["10Y-3M spread"] = rates["10Y yield"] - rates["3M yield"]
    if "DGS10" in avail and "DGS2" in avail:
        rates["10Y-2Y spread"] = rates["10Y yield"] - rates["2Y yield"]
    real_chg = None
    if "DGS10" in avail and "T10YIE" in avail:
        real = (avail["DGS10"] - avail["T10YIE"]).dropna()
        if len(real) > 25:
            rates["10Y real yield"] = float(real.iloc[-1])
            real_chg = float(real.iloc[-1] - real.iloc[-21])
            rates["real_yield_1m_change"] = real_chg
    if "PCEPILFE" in avail and "DFF" in avail and infl.get("Core PCE", {}).get("yoy") is not None:
        rates["real_policy_rate"] = rates["Fed funds"] - infl["Core PCE"]["yoy"]
    out["rates"] = rates

    # ---- Recession probability (model estimate)
    parts = {}
    if "10Y-3M spread" in rates:
        parts["yield_curve"] = _phi(-0.5333 - 0.6330 * rates["10Y-3M spread"])  # Estrella–Mishkin form
    if "SAHMREALTIME" in avail:
        sahm = _last(avail["SAHMREALTIME"])
        parts["sahm_rule"] = float(np.clip(0.05 + sahm / 0.5 * 0.75, 0.02, 0.95))
    if "BAMLH0A0HYM2" in avail:
        oas = _last(avail["BAMLH0A0HYM2"])
        parts["credit_spreads"] = 1 / (1 + exp(-(oas - 5.5) * 1.4))
    w = {"yield_curve": 0.45, "sahm_rule": 0.35, "credit_spreads": 0.20}
    if parts:
        rp = sum(parts[k] * w[k] for k in parts) / sum(w[k] for k in parts)
        out["recession_probability"] = {"value": round(rp, 3), "components": {k: round(v, 3) for k, v in parts.items()},
                                        "note": "12-month model estimate; blend of curve probit, Sahm rule and HY spreads"}

    # ---- Liquidity: Fed net liquidity = balance sheet − TGA − RRP
    if all(k in avail for k in ("WALCL", "WTREGEN", "RRPONTSYD")):
        frame = pd.concat([_bn(avail["WALCL"]), _bn(avail["WTREGEN"]), _bn(avail["RRPONTSYD"])], axis=1).ffill().dropna()
        frame.columns = ["bs", "tga", "rrp"]
        net = (frame["bs"] - frame["tga"] - frame["rrp"]).resample("W-WED").last().dropna()
        if len(net) > 60:
            ch = net.diff(13).dropna()
            ref = ch.tail(156)
            z = float((ch.iloc[-1] - ref.mean()) / (ref.std() or 1))
            out["liquidity"] = {"net_liquidity_bn": round(float(net.iloc[-1]), 1),
                                "change_13w_bn": round(float(ch.iloc[-1]), 1), "z": round(z, 2),
                                "score": int(np.clip(50 + z * 20, 0, 100)),
                                "series": [{"t": t.strftime("%Y-%m-%d"), "v": round(float(v), 1)} for t, v in net.tail(104).items()],
                                "note": "US Fed net liquidity proxy (score 0–100, 50 = average)"}

    # ---- Data impact: how far latest prints sit from their recent trend
    impact = []
    for k in ("CPIAUCSL", "PAYEMS", "RSAFS", "INDPRO", "UNRATE", "PPIFIS"):
        s = avail.get(k)
        if s is None or len(s) < 14:
            continue
        chg = s.diff().dropna() if k in ("PAYEMS", "UNRATE") else s.pct_change().dropna()
        hist = chg.iloc[-13:-1]
        z = float((chg.iloc[-1] - hist.mean()) / (hist.std() or 1))
        impact.append({"indicator": SERIES[k], "z": round(z, 2), "date": out["as_of"][k]})
    out["data_surprises"] = impact
    out["market_impact_score"] = int(min(100, np.mean([abs(i["z"]) for i in impact]) * 40)) if impact else None

    # ---- Regime
    inf_up = infl_delta > 0
    gr_up = growth > 0
    out["regime"] = {(True, False): "Goldilocks (growth ↑, inflation ↓)", (True, True): "Reflation (growth ↑, inflation ↑)",
                     (False, True): "Stagflation risk (growth ↓, inflation ↑)", (False, False): "Disinflationary slowdown (growth ↓, inflation ↓)"}[(gr_up, inf_up)]
    out["factors"] = {"growth": growth, "inflation": np.clip(infl_delta / 1.5, -1, 1).item(),
                      "liquidity": (out.get("liquidity", {}).get("z", 0) or 0) / 2,
                      "recession": out.get("recession_probability", {}).get("value", 0.3),
                      "real_yield_change": real_chg or 0.0}
    out["central_banks"] = load_central_banks()
    if "DFF" in avail:
        out["central_banks"]["banks"]["USD"]["rate"] = round(rates["Fed funds"], 2)
        out["central_banks"]["banks"]["USD"]["source"] = "FRED DFF (live)"
    return out


def _fx_signals(symbol: str, snap: dict) -> list[Signal]:
    pair = fx_currencies(symbol)
    banks = snap["central_banks"]["banks"]
    if not pair or pair[0] not in banks or pair[1] not in banks:
        return []
    b, q = banks[pair[0]], banks[pair[1]]
    diff = b["rate"] - q["rate"]
    bias_map = {"hiking": 1, "hawkish hold": 0.5, "hold": 0, "dovish hold": -0.5, "cutting": -1}
    pol = bias_map.get(b["bias"], 0) - bias_map.get(q["bias"], 0)
    sig = [
        Signal(name="Policy-rate differential", value=f"{pair[0]} {b['rate']}% vs {pair[1]} {q['rate']}%",
               impact=round(float(np.clip(diff * 6, -25, 25)), 1), note="carry favours the higher-yielding currency"),
        Signal(name="Policy direction", value=f"{b['bias']} vs {q['bias']}", impact=round(pol * 15, 1),
               note="relative hawkishness drives rate expectations"),
    ]
    infl_b, infl_q = b.get("inflation"), q.get("inflation")
    if infl_b is not None and infl_q is not None:
        real_diff = (b["rate"] - infl_b) - (q["rate"] - infl_q)
        sig.append(Signal(name="Real-rate differential", value=round(real_diff, 2),
                          impact=round(float(np.clip(real_diff * 5, -15, 15)), 1)))
    usd_sign = 1 if pair[0] == "USD" else -1 if pair[1] == "USD" else 0
    if usd_sign:
        rc = snap["factors"]["real_yield_change"]
        sig.append(Signal(name="US real yields (1m)", value=f"{rc:+.2f}pp",
                          impact=round(float(np.clip(rc * 60, -12, 12)) * usd_sign, 1)))
        rp = snap["factors"]["recession"]
        risk_ccy = {"AUD", "NZD", "CAD"}
        other = pair[1] if usd_sign > 0 else pair[0]
        if other in risk_ccy:  # USD tends to outperform pro-cyclicals when recession risk is high
            sig.append(Signal(name="Risk-cycle", value=f"recession p={rp:.0%}",
                              impact=round(float((rp - 0.3) * 30) * usd_sign, 1)))
    return sig


def analyze(symbol: str, snap: dict | None) -> ModuleResult:
    if not snap or not snap.get("factors"):
        return unavailable("macro", "macro data unavailable")
    f = snap["factors"]
    ac = asset_class(symbol)
    g, inf, liq, rp, ry = f["growth"], f["inflation"], f["liquidity"], f["recession"], f["real_yield_change"]
    s: list[Signal] = []
    if ac == "forex":
        s = _fx_signals(symbol, snap)
    elif ac in ("stock", "index"):
        s = [Signal(name="Growth momentum", value=snap["growth"]["label"], impact=round(g * 25, 1)),
             Signal(name="Liquidity", value=snap.get("liquidity", {}).get("score"), impact=round(np.clip(liq, -1, 1) * 20, 1)),
             Signal(name="Recession risk", value=f"{rp:.0%}", impact=round((0.3 - rp) * 40, 1)),
             Signal(name="Real yields (1m)", value=f"{ry:+.2f}pp", impact=round(float(np.clip(-ry * 50, -12, 12)), 1)),
             Signal(name="Inflation trend", value=snap["inflation"]["direction"], impact=round(-inf * 10, 1))]
    elif symbol.upper() in ("GC=F", "SI=F", "PL=F"):
        s = [Signal(name="Real yields (1m)", value=f"{ry:+.2f}pp", impact=round(float(np.clip(-ry * 90, -30, 30)), 1),
                    note="precious metals move inversely to real yields"),
             Signal(name="Liquidity", value=snap.get("liquidity", {}).get("score"), impact=round(np.clip(liq, -1, 1) * 15, 1)),
             Signal(name="Recession hedge demand", value=f"{rp:.0%}", impact=round((rp - 0.3) * 25, 1)),
             Signal(name="Inflation trend", value=snap["inflation"]["direction"], impact=round(inf * 12, 1))]
    elif ac == "commodity":
        s = [Signal(name="Growth momentum", value=snap["growth"]["label"], impact=round(g * 30, 1)),
             Signal(name="Inflation trend", value=snap["inflation"]["direction"], impact=round(inf * 12, 1)),
             Signal(name="Recession risk", value=f"{rp:.0%}", impact=round((0.3 - rp) * 30, 1))]
    elif ac == "crypto":
        s = [Signal(name="Liquidity", value=snap.get("liquidity", {}).get("score"), impact=round(np.clip(liq, -1, 1) * 35, 1),
                    note="crypto is the most liquidity-sensitive asset class"),
             Signal(name="Real yields (1m)", value=f"{ry:+.2f}pp", impact=round(float(np.clip(-ry * 50, -15, 15)), 1)),
             Signal(name="Growth momentum", value=snap["growth"]["label"], impact=round(g * 10, 1))]
    if not s:
        return unavailable("macro", f"no macro mapping for {symbol}")
    return finish("macro", s, coverage=0.85, details={"regime": snap["regime"]}, cap=90)
