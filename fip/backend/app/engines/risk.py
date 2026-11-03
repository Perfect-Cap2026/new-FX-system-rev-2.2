"""Module 9 — Risk: position sizing, prop-firm guardrails, A+ gate."""
from dataclasses import dataclass

from app.providers.base import asset_class

FUTURES_MULT = {"GC=F": 100, "SI=F": 5000, "CL=F": 1000, "NG=F": 10000, "ES=F": 50, "NQ=F": 20, "HG=F": 25000}


@dataclass
class Account:
    equity: float
    risk_pct: float
    max_daily_loss_pct: float
    max_total_dd_pct: float
    min_rr: float
    daily_pnl: float = 0.0
    peak_equity: float | None = None


def position_size(symbol: str, entry: float, stop: float, account: Account) -> dict:
    risk_cash = account.equity * account.risk_pct / 100
    per_unit = abs(entry - stop)
    if per_unit <= 0:
        return {"error": "stop equals entry"}
    units = risk_cash / per_unit
    ac = asset_class(symbol)
    out = {"risk_cash": round(risk_cash, 2), "units": round(units, 4), "asset_class": ac}
    if ac == "forex":
        quote = symbol.upper().replace("=X", "")[-3:]
        out["lots"] = round(units / 100_000, 2)
        out["note"] = (f"P&L is in {quote}; convert risk_cash to {quote} for exact sizing"
                       if quote != "USD" else "standard lot = 100,000 units")
    elif symbol.upper() in FUTURES_MULT:
        out["contracts"] = round(units / FUTURES_MULT[symbol.upper()], 2)
        out["note"] = f"contract multiplier {FUTURES_MULT[symbol.upper()]}"
    out["notional"] = round(units * entry, 2)
    out["leverage"] = round(out["notional"] / account.equity, 2)
    return out


def evaluate(symbol: str, setup: dict | None, account: Account, decision: dict | None = None,
             module_labels: dict | None = None, high_impact_event_soon: bool = False) -> dict:
    checks = []

    def chk(name, ok, detail):
        checks.append({"check": name, "pass": bool(ok), "detail": detail})

    if not setup:
        return {"approved": False, "grade": "No setup", "checks": [], "reason": "no directional trade setup"}

    size = position_size(symbol, setup["entry"], setup["stop"], account)
    rr1 = setup["rr"][0] if setup.get("rr") else 0
    best_rr = max(setup.get("rr", [0]))
    chk("Reward:risk", best_rr >= account.min_rr, f"T1 {rr1}R, best {best_rr}R (min {account.min_rr}R)")
    chk("Risk per trade", account.risk_pct <= 1.0, f"{account.risk_pct}% of equity")
    dd_room = account.equity * account.max_daily_loss_pct / 100 + account.daily_pnl
    chk("Daily loss room", size.get("risk_cash", 0) <= dd_room * 0.5,
        f"trade risk {size.get('risk_cash')} vs remaining daily room {round(dd_room, 2)}")
    if account.peak_equity:
        dd = (account.peak_equity - account.equity) / account.peak_equity * 100
        chk("Total drawdown", dd < account.max_total_dd_pct * 0.8, f"{dd:.2f}% of {account.max_total_dd_pct}% limit")
    chk("Leverage", size.get("leverage", 0) <= 30, f"{size.get('leverage')}x notional")
    chk("News blackout", not high_impact_event_soon, "no high-impact event within 30 min" if not high_impact_event_soon
        else "high-impact event imminent")

    if decision:
        chk("Composite strength", abs(decision["composite"]) >= 35, f"composite {decision['composite']}")
        chk("Confidence", decision["confidence"] >= 0.6, f"confidence {decision['confidence']}")
        dir_sign = 1 if setup["direction"] == "long" else -1
        chk("Direction matches bias", decision["composite"] * dir_sign > 0, decision["bias"])
    if module_labels:
        t, i = module_labels.get("technical", ""), module_labels.get("institutional", "")
        agree = ("Bull" in t and "Bull" in i) or ("Bear" in t and "Bear" in i)
        chk("Technical & institutional agree", agree, f"technical {t}, institutional {i}")

    failed = [c for c in checks if not c["pass"]]
    grade = "A+" if not failed else "A" if len(failed) == 1 else "B" if len(failed) == 2 else "C"
    return {"approved": grade == "A+", "grade": grade, "checks": checks, "position": size,
            "reason": "all checks passed" if not failed else "; ".join(c["check"] for c in failed) + " failed"}
