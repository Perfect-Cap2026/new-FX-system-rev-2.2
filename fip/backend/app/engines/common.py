from typing import Any

import numpy as np
from pydantic import BaseModel, Field


class Signal(BaseModel):
    name: str
    value: Any = None
    impact: float = 0.0  # contribution, −100..+100 scale
    note: str = ""


class ModuleResult(BaseModel):
    module: str
    available: bool = True
    score: float = 0.0
    confidence: float = 0.0
    label: str = "Neutral"
    signals: list[Signal] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


def label_for(score: float) -> str:
    a = abs(score)
    if a < 15:
        return "Neutral"
    side = "Bullish" if score > 0 else "Bearish"
    return f"Strong {side}" if a > 50 else side


def clamp(x: float, lo: float = -100, hi: float = 100) -> float:
    return float(max(lo, min(hi, x)))


def unavailable(module: str, reason: str) -> ModuleResult:
    return ModuleResult(module=module, available=False, label="N/A", details={"reason": reason})


def finish(module: str, signals: list[Signal], coverage: float = 1.0, details: dict | None = None,
           cap: float = 100) -> ModuleResult:
    """Score = sum of signal impacts (clamped). Confidence = coverage × sign agreement among signals."""
    if not signals:
        return unavailable(module, "no signals")
    score = clamp(sum(s.impact for s in signals), -cap, cap)
    nonzero = [s.impact for s in signals if abs(s.impact) > 1e-9]
    if nonzero and score != 0:
        agree = sum(np.sign(i) == np.sign(score) for i in nonzero) / len(nonzero)
    else:
        agree = 0.5
    conf = float(np.clip(coverage * (0.35 + 0.65 * agree), 0, 1))
    return ModuleResult(module=module, score=round(score, 1), confidence=round(conf, 2),
                        label=label_for(score), signals=signals, details=details or {})


def py(x):
    """numpy → JSON-safe python."""
    if isinstance(x, (np.floating,)):
        return None if np.isnan(x) else round(float(x), 6)
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, float):
        return None if np.isnan(x) else round(x, 6)
    return x
