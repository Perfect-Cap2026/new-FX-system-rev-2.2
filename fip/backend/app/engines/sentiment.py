"""Module 6 — Sentiment: finance-lexicon headline scoring + analyst consensus.

Lexicon approach (Loughran–McDonald style) is transparent and fast; Phase 3 adds an LLM classifier
for central-bank statements and earnings calls.
"""
import re

import numpy as np

from app.engines.common import ModuleResult, Signal, finish, unavailable

POS = {
    "beat", "beats", "surge", "surges", "soar", "soars", "rally", "rallies", "gain", "gains", "jump", "jumps",
    "record", "upgrade", "upgrades", "upgraded", "strong", "stronger", "growth", "outperform", "bullish", "boost",
    "boosts", "rise", "rises", "rising", "higher", "optimism", "optimistic", "recovery", "rebound", "rebounds",
    "profit", "profits", "exceed", "exceeds", "expands", "expansion", "buy", "accelerate", "accelerates", "upside",
    "robust", "resilient", "breakthrough", "approval", "approved", "dovish", "easing", "stimulus", "climbs",
}
NEG = {
    "miss", "misses", "plunge", "plunges", "slump", "slumps", "fall", "falls", "drop", "drops", "decline", "declines",
    "downgrade", "downgrades", "downgraded", "weak", "weaker", "loss", "losses", "bearish", "cut", "cuts", "lower",
    "fear", "fears", "risk", "risks", "recession", "slowdown", "slowing", "crisis", "lawsuit", "probe", "investigation",
    "sell", "selloff", "sell-off", "tumble", "tumbles", "sink", "sinks", "warning", "warns", "default", "bankruptcy",
    "layoffs", "tariff", "tariffs", "sanctions", "war", "hawkish", "inflation", "volatile", "uncertainty", "slides",
}
NEGATORS = {"not", "no", "never", "without", "despite", "fails", "failed"}
TOKEN = re.compile(r"[a-z][a-z\-]+")

# Geopolitical risk vocabulary — counted separately for the dashboard risk panel
GEO = {"war", "sanctions", "tariff", "tariffs", "conflict", "missile", "invasion", "election", "embargo",
       "strike", "coup", "ceasefire", "opec", "escalation", "attack", "nuclear", "blockade"}


def score_text(text: str) -> tuple[float, int]:
    toks = TOKEN.findall(text.lower())
    s, hits = 0.0, 0
    for i, t in enumerate(toks):
        pol = 1 if t in POS else -1 if t in NEG else 0
        if pol:
            if any(w in NEGATORS for w in toks[max(0, i - 3):i]):
                pol = -pol
            s += pol
            hits += 1
    return (s / max(hits, 1)), hits


def classify(score: float) -> str:
    if score > 50:
        return "Strong Bullish"
    if score > 15:
        return "Bullish"
    if score < -50:
        return "Strong Bearish"
    if score < -15:
        return "Bearish"
    return "Neutral"


def analyze(news: list[dict], fund: dict, price: float | None = None) -> ModuleResult:
    sig: list[Signal] = []
    scored = []
    geo_hits = []
    for n in news:
        text = f"{n.get('title', '')}. {n.get('summary', '')}"
        sc, hits = score_text(text)
        scored.append({**n, "sentiment": round(sc, 2), "hits": hits})
        g = GEO & set(TOKEN.findall(text.lower()))
        if g:
            geo_hits.append({"title": n.get("title"), "terms": sorted(g)})
    with_hits = [x for x in scored if x["hits"] > 0]
    if with_hits:
        avg = float(np.mean([x["sentiment"] for x in with_hits]))
        sig.append(Signal(name="News flow", value=f"{len(with_hits)} scored headlines", impact=round(avg * 45, 1),
                          note=f"mean polarity {avg:+.2f}"))

    rec = fund.get("recommendationMean")
    if rec:
        n = fund.get("numberOfAnalystOpinions") or 0
        sig.append(Signal(name="Analyst consensus", value=f"{rec:.2f} (1=Strong Buy, 5=Sell), {n} analysts",
                          impact=round(float(np.clip((2.6 - rec) * 18, -20, 20)), 1)))
    tgt = fund.get("targetMeanPrice")
    if tgt and price:
        up = tgt / price - 1
        sig.append(Signal(name="Analyst target upside", value=f"{up:+.1%}", impact=round(float(np.clip(up * 80, -12, 12)), 1)))

    if not sig:
        return unavailable("sentiment", "no news or analyst data")
    res = finish("sentiment", sig, coverage=min(1.0, 0.3 + 0.07 * len(with_hits) + (0.2 if rec else 0)),
                 details={"headlines": sorted(scored, key=lambda x: -abs(x["sentiment"]))[:12], "geopolitical": geo_hits[:8]})
    res.label = classify(res.score)
    return res
