"""Analysis orchestrator: fetch → engines → decision → risk → thesis. Routes stay thin."""
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pandas as pd

from app import providers as P
from app.core.cache import cached
from app.core.config import get_settings
from app.engines import decision, fundamental, intermarket, macro, micro, risk, sentiment, smc, technical
from app.providers.base import INTERMARKET, SECTORS, asset_class

log = logging.getLogger(__name__)
# Three tiers so nested waits can never deadlock: dashboard → composite tasks → leaf I/O
_io = ThreadPoolExecutor(max_workers=16, thread_name_prefix="io")
_task = ThreadPoolExecutor(max_workers=4, thread_name_prefix="task")
_outer = ThreadPoolExecutor(max_workers=4, thread_name_prefix="outer")


def macro_snapshot() -> dict:
    def build():
        data = macro.fetch_all(P.fred)
        if sum(len(v) > 0 for v in data.values()) < 5:
            return None
        return macro.snapshot(data)
    return cached("macro:snapshot", 3600, build) or {}


def basket_closes() -> dict[str, pd.Series]:
    futs = {name: _io.submit(P.bars, sym, "1d", 400) for name, sym in INTERMARKET.items()}
    out = {}
    for name, f in futs.items():
        df = f.result()
        if df is not None and not df.empty:
            out[name] = df["close"]
    return out


def intermarket_overview() -> dict:
    def build():
        closes = basket_closes()
        if "S&P 500" not in closes:
            return None
        _, extra = intermarket.analyze("S&P 500", closes["S&P 500"], closes, INTERMARKET)
        if not extra:
            return None
        perf = {}
        for k, s in closes.items():
            if len(s) > 22:
                perf[k] = {"last": round(float(s.iloc[-1]), 4), "chg_1d": round(float(s.iloc[-1] / s.iloc[-2] - 1), 4),
                           "chg_1m": round(float(s.iloc[-1] / s.iloc[-22] - 1), 4)}
        return extra | {"performance": perf}
    return cached("intermarket:overview", 900, build) or {}


def sectors() -> dict:
    def build():
        futs = {s: _io.submit(P.bars, s, "1d", 300) for s in list(SECTORS) + ["SPY"]}
        closes = {s: f.result()["close"] for s, f in futs.items() if not f.result().empty}
        bench = closes.pop("SPY", None)
        return micro.analyze(closes, bench) if bench is not None else None
    return cached("sectors", 1800, build) or {"rankings": [], "phase": None}


def _account() -> risk.Account:
    s = get_settings()
    return risk.Account(s.account_equity, s.risk_per_trade_pct, s.max_daily_loss_pct, s.max_total_drawdown_pct, s.min_rr)


def analyze_symbol(symbol: str, with_thesis: bool = True) -> dict:
    key = f"analysis:{symbol}:{int(with_thesis)}"
    return cached(key, 300, lambda: _analyze(symbol, with_thesis))


def _analyze(symbol: str, with_thesis: bool) -> dict | None:
    s = get_settings()
    f_bars = {tf: _io.submit(P.bars, symbol, tf, 600) for tf in ("1h", "1d", "1wk")}
    f_fund = _io.submit(P.fundamentals, symbol) if asset_class(symbol) in ("stock", "index") else None
    f_news = _io.submit(P.news, symbol)
    f_macro = _task.submit(macro_snapshot)
    f_basket = _task.submit(basket_closes)

    frames = {tf: f.result() for tf, f in f_bars.items()}
    daily = frames["1d"]
    if daily is None or daily.empty or len(daily) < 60:
        return None
    fund = f_fund.result() if f_fund else {}
    snap = f_macro.result()
    basket = f_basket.result()
    price = float(daily["close"].iloc[-1])
    month = datetime.now(timezone.utc).month

    results = {
        "macro": macro.analyze(symbol, snap),
        "fundamental": fundamental.analyze(symbol, fund, daily, frames.get("1wk"), snap, month),
        "institutional": smc.analyze(daily),
        "technical": technical.analyze(frames),
        "sentiment": sentiment.analyze(f_news.result(), fund, price),
    }
    target_name = next((n for n, sy in INTERMARKET.items() if sy == symbol), symbol)
    results["intermarket"], im_extra = intermarket.analyze(target_name, daily["close"], basket, INTERMARKET | {symbol: symbol})

    dec = decision.combine(results, s.weights)
    setup = results["technical"].details.get("setup") if results["technical"].available else None
    labels = {k: r.label for k, r in results.items()}
    risk_eval = risk.evaluate(symbol, setup, _account(), dec, labels)

    name = fund.get("shortName") or symbol
    regime = snap.get("regime") if snap else None
    thesis = decision.template_thesis(symbol, name, dec, results, setup, regime)
    thesis_source = "template"
    if with_thesis and s.anthropic_api_key:
        payload = {"decision": dec, "setup": setup, "risk": {k: risk_eval[k] for k in ("grade", "reason")},
                   "macro_regime": regime,
                   "modules": {k: {"score": r.score, "label": r.label, "signals": [sg.model_dump() for sg in r.signals]}
                               for k, r in results.items() if r.available}}
        llm = decision.llm_thesis(s.anthropic_api_key, s.anthropic_model, symbol, payload)
        if llm:
            thesis, thesis_source = llm, s.anthropic_model

    prev = float(daily["close"].iloc[-2])
    return {
        "symbol": symbol, "name": name, "asset_class": asset_class(symbol),
        "price": price, "change_1d": round(price / prev - 1, 5),
        "as_of": daily.index[-1].isoformat(), "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_provider": s.data_provider,
        "decision": dec, "modules": {k: r.model_dump() for k, r in results.items()},
        "trade_setup": setup, "risk": risk_eval,
        "thesis": thesis, "thesis_source": thesis_source,
        "disclaimer": "Model output for research only — not investment advice.",
    }


def _rank_row(r: dict) -> dict:
    d = r["decision"]
    return {"symbol": r["symbol"], "name": r["name"], "asset_class": r["asset_class"], "price": r["price"],
            "change_1d": r["change_1d"], "composite": d["composite"], "confidence": d["confidence"], "bias": d["bias"],
            "action": d["action"], "grade": r["risk"]["grade"],
            "conviction": round(abs(d["composite"]) * d["confidence"], 1),
            "modules": {k: m["score"] if m["available"] else None for k, m in r["modules"].items()},
            "setup": r["trade_setup"]}


def portfolio_suggestions(rows: list[dict], reports: dict[str, dict], max_positions: int = 5) -> list[dict]:
    picks, closes = [], {}
    for sym, rep in reports.items():
        ser = rep["modules"]["technical"]["details"].get("series", [])
        if ser:
            closes[sym] = pd.Series([p["c"] for p in ser], index=pd.to_datetime([p["t"] for p in ser]))
    rets = pd.DataFrame(closes).pct_change().dropna(how="all")
    for row in sorted(rows, key=lambda r: -r["conviction"]):
        if row["action"] not in ("Buy", "Sell") and not row["action"].startswith("Lean"):
            continue
        sign = 1 if row["composite"] > 0 else -1
        redundant = False
        for p in picks:
            if row["symbol"] in rets and p["symbol"] in rets:
                rho = rets[row["symbol"]].corr(rets[p["symbol"]])
                if pd.notna(rho) and rho * sign * p["sign"] > 0.75:
                    redundant = True
                    break
        if redundant:
            continue
        picks.append({"symbol": row["symbol"], "direction": "long" if sign > 0 else "short", "sign": sign,
                      "conviction": row["conviction"], "action": row["action"]})
        if len(picks) >= max_positions:
            break
    total = sum(p["conviction"] for p in picks) or 1
    for p in picks:
        p["weight"] = round(min(0.35, p["conviction"] / total), 3)
        p.pop("sign")
    return picks


def dashboard(symbols: list[str]) -> dict:
    def build():
        futs = {sym: _outer.submit(analyze_symbol, sym, False) for sym in symbols}
        reports = {}
        for sym, f in futs.items():
            try:
                rep = f.result()
                if rep:
                    reports[sym] = rep
            except Exception:
                log.exception("analysis failed", extra={"symbol": sym})
        snap = macro_snapshot()
        im = intermarket_overview()
        sec = sectors()
        rows = sorted((_rank_row(r) for r in reports.values()), key=lambda x: -x["conviction"])
        opps = [r for r in rows if r["action"] in ("Buy", "Sell")]
        geo = []
        for rep in reports.values():
            geo += rep["modules"]["sentiment"]["details"].get("geopolitical", []) if rep["modules"]["sentiment"]["available"] else []
        seen, geo_u = set(), []
        for g in geo:
            if g["title"] not in seen:
                seen.add(g["title"])
                geo_u.append(g)

        rp = (snap.get("recession_probability") or {}).get("value")
        reg = (im.get("regime") or {}).get("label")
        bulls = sum(r["composite"] > 15 for r in rows)
        bears = sum(r["composite"] < -15 for r in rows)
        summary = [
            f"Macro regime: {snap.get('regime', 'n/a')}; inflation {snap.get('inflation', {}).get('direction', 'n/a').lower()}, "
            f"growth {snap.get('growth', {}).get('label', 'n/a').lower()}."
            + (f" 12-month recession model estimate {rp:.0%}." if rp is not None else ""),
            f"Cross-asset regime: {reg or 'n/a'}" + (f" ({', '.join(im['regime']['notes'])})." if im.get("regime") else "."),
            f"Watchlist breadth: {bulls} bullish, {bears} bearish, {len(rows) - bulls - bears} neutral of {len(rows)}.",
            (f"Highest conviction: {rows[0]['symbol']} — {rows[0]['bias']} ({rows[0]['composite']:+.0f}), {rows[0]['action']}."
             if rows else "No assets analysed."),
            f"{len(opps)} setup(s) clear the Buy/Sell threshold; {sum(r['grade'] == 'A+' for r in rows)} pass the A+ risk gate.",
        ]
        if sec.get("phase"):
            summary.append(f"Sector leadership points to: {sec['phase']}.")
        vix = (im.get("performance") or {}).get("VIX", {}).get("last")
        risk_panel = {
            "regime": reg, "vix": vix, "recession_probability": rp,
            "liquidity_score": (snap.get("liquidity") or {}).get("score"),
            "hy_spread": (snap.get("rates") or {}).get("HY OAS"),
            "curve_10y_3m": (snap.get("rates") or {}).get("10Y-3M spread"),
            "warnings": [w for w in [
                "VIX elevated (>22)" if vix and vix > 22 else None,
                "Yield curve inverted (10Y-3M < 0)" if (snap.get("rates") or {}).get("10Y-3M spread", 1) < 0 else None,
                "Recession model > 40%" if rp and rp > 0.4 else None,
                "Liquidity contracting" if (snap.get("liquidity") or {}).get("z", 0) < -1 else None,
            ] if w],
        }
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "executive_summary": summary,
            "macro": {k: snap.get(k) for k in ("regime", "inflation", "growth", "rates", "recession_probability",
                                               "market_impact_score", "data_surprises")}
                     | {"liquidity": {k: v for k, v in (snap.get("liquidity") or {}).items() if k != "series"}},
            "central_banks": snap.get("central_banks"),
            "rankings": rows, "opportunities": opps,
            "sectors": sec, "intermarket": {k: im.get(k) for k in ("regime", "performance")},
            "geopolitical": geo_u[:10], "risk": risk_panel,
            "portfolio": portfolio_suggestions(rows, reports),
        }
    return cached(f"dashboard:{','.join(symbols)}", 300, build)
