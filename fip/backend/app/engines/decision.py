"""Module 8 — AI decision engine: weighted composite, action, thesis."""
import json
import logging

import numpy as np

from app.engines.common import ModuleResult, label_for

log = logging.getLogger(__name__)


def combine(results: dict[str, ModuleResult], weights: dict[str, float]) -> dict:
    used = {k: r for k, r in results.items() if r.available and k in weights}
    if not used:
        return {"composite": 0.0, "confidence": 0.0, "bias": "Neutral", "action": "No trade",
                "contributions": {}, "coverage": 0.0}
    num = sum(weights[k] * r.score * max(r.confidence, 0.05) for k, r in used.items())
    den = sum(weights[k] * max(r.confidence, 0.05) for k, r in used.items())
    composite = num / den
    coverage = sum(weights[k] for k in used) / sum(weights.values())
    signs = [np.sign(r.score) for r in used.values() if abs(r.score) >= 10]
    agreement = (sum(s == np.sign(composite) for s in signs) / len(signs)) if signs else 0.5
    mean_conf = float(np.mean([r.confidence for r in used.values()]))
    confidence = float(np.clip(mean_conf * (0.5 + 0.5 * agreement) * (0.6 + 0.4 * coverage), 0, 1))

    if abs(composite) >= 35 and confidence >= 0.55:
        action = "Buy" if composite > 0 else "Sell"
    elif abs(composite) >= 15:
        action = "Lean long — wait for trigger" if composite > 0 else "Lean short — wait for trigger"
    else:
        action = "No trade"

    contrib = {k: {"score": r.score, "weight": weights[k], "effective_weight": round(weights[k] * max(r.confidence, 0.05) / den, 3),
                   "contribution": round(weights[k] * r.score * max(r.confidence, 0.05) / den, 1), "label": r.label}
               for k, r in used.items()}
    return {"composite": round(composite, 1), "confidence": round(confidence, 2), "bias": label_for(composite),
            "action": action, "agreement": round(agreement, 2), "coverage": round(coverage, 2),
            "contributions": contrib, "missing": [k for k in weights if k not in used]}


def template_thesis(symbol: str, name: str, decision: dict, results: dict[str, ModuleResult], setup: dict | None,
                    regime: str | None) -> str:
    def top(mod, n=2, positive=True):
        r = results.get(mod)
        if not r or not r.available:
            return []
        sig = sorted(r.signals, key=lambda s: -s.impact if positive else s.impact)
        return [s for s in sig if (s.impact > 0) == positive and abs(s.impact) >= 3][:n]

    side = decision["composite"] >= 0
    support = [s for m in results for s in top(m, 2, side)]
    against = [s for m in results for s in top(m, 1, not side)]
    support.sort(key=lambda s: -abs(s.impact))
    against.sort(key=lambda s: -abs(s.impact))
    lines = [f"**{name} — {decision['bias']} (composite {decision['composite']:+.0f}, confidence {decision['confidence']:.0%}).**"]
    if regime:
        lines.append(f"Macro regime: {regime}.")
    if support:
        lines.append("Supporting evidence: " + "; ".join(f"{s.name} ({s.value})" for s in support[:4]) + ".")
    if against:
        lines.append("Risks to the view: " + "; ".join(f"{s.name} ({s.value})" for s in against[:3]) + ".")
    if setup and decision["action"] in ("Buy", "Sell"):
        lines.append(f"Plan: {setup['direction']} {setup['entry_type']} at {setup['entry']:.5g}, stop {setup['stop']:.5g}, "
                     f"targets {', '.join(f'{t:.5g}' for t in setup['targets'])} ({setup['rr'][0]}R / {setup['rr'][1]}R / {setup['rr'][2]}R).")
    elif decision["action"].startswith("Lean"):
        lines.append("Signals lean one way but don't clear the conviction threshold — wait for structure confirmation on the lower timeframe.")
    else:
        lines.append("No edge: modules disagree or signals are weak. Stand aside.")
    if decision.get("missing"):
        lines.append(f"Not scored: {', '.join(decision['missing'])} (weights renormalised).")
    return " ".join(lines)


def llm_thesis(api_key: str, model: str, symbol: str, payload: dict) -> str | None:
    """Ask Claude to write the thesis from structured signals only. Numbers must come from the payload."""
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        prompt = (
            "You are the CIO of a macro hedge fund writing a concise investment thesis (max 180 words) for "
            f"{symbol}. Use ONLY the structured analysis below; do not invent prices, data or events. "
            "Structure: 1) view and conviction, 2) the three strongest drivers, 3) key risks / what would invalidate, "
            "4) the trade plan if action is Buy/Sell. Plain prose, no headers.\n\n"
            + json.dumps(payload, default=str)[:12000]
        )
        msg = client.messages.create(model=model, max_tokens=500, messages=[{"role": "user", "content": prompt}])
        return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip() or None
    except Exception as e:
        log.warning(f"LLM thesis failed: {e}")
        return None
