import numpy as np
import pandas as pd
import pytest

from app.engines import decision, indicators as ind, intermarket, risk, sentiment, smc, technical
from app.engines.common import ModuleResult, label_for
from app.providers.base import asset_class, fx_currencies, validate_symbol
from app.providers.synthetic import make_ohlcv


def trend(drift, n=600, seed=1, freq="B"):
    return make_ohlcv(n, 100.0, drift, 0.006, seed, freq)


# ---------- helpers / providers
@pytest.mark.parametrize("sym,cls", [("EURUSD=X", "forex"), ("GC=F", "commodity"), ("ES=F", "index"),
                                     ("^GSPC", "index"), ("BTC-USD", "crypto"), ("AAPL", "stock")])
def test_asset_class(sym, cls):
    assert asset_class(sym) == cls


def test_fx_currencies():
    assert fx_currencies("EURUSD=X") == ("EUR", "USD")
    assert fx_currencies("JPY=X") == ("USD", "JPY")


@pytest.mark.parametrize("bad", ["", "DROP TABLE;", "../etc/passwd", "A" * 30])
def test_symbol_validation_rejects(bad):
    with pytest.raises(ValueError):
        validate_symbol(bad)


def test_labels():
    assert label_for(0) == "Neutral" and label_for(30) == "Bullish" and label_for(-70) == "Strong Bearish"


# ---------- indicators
def test_rsi_bounds_and_direction():
    up = ind.rsi(trend(0.004)["close"])
    dn = ind.rsi(trend(-0.004)["close"])
    assert up.between(0, 100).all() and dn.between(0, 100).all()
    assert up.tail(50).mean() > 55 > 45 > dn.tail(50).mean()


def test_atr_positive():
    assert (ind.atr(trend(0.001)).dropna() > 0).all()


def test_volume_profile_value_area_contains_poc():
    vp = ind.volume_profile(trend(0.0, 300))
    assert vp["val"] <= vp["poc"] <= vp["vah"]


def test_support_resistance_sides():
    df = trend(0.0, 400, seed=7)
    lv = ind.support_resistance(df, float(ind.atr(df).iloc[-1]))
    last = df["close"].iloc[-1]
    assert all((l["type"] == "support") == (l["price"] <= last) for l in lv)


# ---------- technical
def test_technical_uptrend_is_bullish_with_valid_long_setup():
    res = technical.analyze({"1d": trend(0.003), "1wk": trend(0.004, 300, 2, "W-FRI"), "1h": trend(0.001, 600, 3, "h")})
    assert res.available and res.score > 15
    s = res.details["setup"]
    assert s["direction"] == "long" and s["stop"] < s["entry"] < s["targets"][0] <= s["targets"][1] <= s["targets"][2]


def test_technical_downtrend_is_bearish_with_valid_short_setup():
    res = technical.analyze({"1d": trend(-0.003), "1wk": trend(-0.004, 300, 2, "W-FRI")})
    assert res.score < -15
    s = res.details["setup"]
    assert s["direction"] == "short" and s["stop"] > s["entry"] > s["targets"][0]


def test_technical_unavailable_on_short_history():
    assert not technical.analyze({"1d": trend(0.001, 30)}).available


# ---------- smart money
def _gap_frame():
    df = trend(0.0, 200, seed=11).copy()
    i = 150  # inject a bullish 3-candle imbalance well clear of later prices
    jump = df["high"].iloc[i - 2] * 0.05
    df.iloc[i:, :4] = df.iloc[i:, :4] + jump
    return df


def test_fvg_detected_on_injected_gap():
    df = _gap_frame()
    gaps = smc.fair_value_gaps(df, float(ind.atr(df).iloc[-1]), keep=20)
    assert any(g["dir"] == "bullish" and g["i"] == 150 for g in gaps)


def test_structure_events_bullish_in_uptrend():
    df = trend(0.004, 300)
    events, state = smc.structure_events(df, smc.swings(df))
    assert events and state[-1] == 1


def test_smc_module_scores_uptrend_positive():
    res = smc.analyze(trend(0.004, 400))
    assert res.available and res.score > 0
    assert "probability_matrix" in res.details


# ---------- sentiment
def test_sentiment_polarity_and_negation():
    assert sentiment.score_text("Shares surge after earnings beat")[0] > 0
    assert sentiment.score_text("Stock plunges on profit warning")[0] < 0
    assert sentiment.score_text("Company did not beat estimates")[0] < 0


def test_sentiment_classes():
    res = sentiment.analyze([{"title": "Record profits, strong growth and upgrade"}], {"recommendationMean": 1.5})
    assert res.label in ("Bullish", "Strong Bullish")


# ---------- intermarket
def test_correlation_matrix_detects_identical_series():
    a = trend(0.001, 300, 5)["close"]
    b = a * 2
    c = trend(0.0, 300, 99)["close"]
    res, extra = intermarket.analyze("A", a, {"B": b, "C": c}, {})
    m = extra["correlation_matrix"]
    i, j = m["assets"].index("A"), m["assets"].index("B")
    assert m["values"][i][j] == pytest.approx(1.0, abs=1e-6)
    assert extra["drivers"][0]["asset"] == "B"


def test_lead_lag_finds_shift():
    rng = np.random.default_rng(0)
    idx = pd.bdate_range("2024-01-01", periods=300)
    x = pd.Series(rng.normal(0, 1, 300), index=idx)
    r = pd.DataFrame({"T": x, "L": x.shift(-2)}).dropna()  # L moves 2 days before T
    ll = intermarket.lead_lag(r, "T")
    assert ll[0]["best_lag"] == 2


# ---------- decision
def _mr(name, score, conf=0.8, avail=True):
    return ModuleResult(module=name, score=score, confidence=conf, available=avail)


W = {"macro": .25, "fundamental": .2, "institutional": .2, "technical": .15, "sentiment": .1, "intermarket": .1}


def test_decision_strong_agreement_buys():
    d = decision.combine({k: _mr(k, 60) for k in W}, W)
    assert d["action"] == "Buy" and d["composite"] == pytest.approx(60)


def test_decision_renormalises_missing_modules():
    res = {k: _mr(k, 50) for k in W}
    res["fundamental"] = _mr("fundamental", 0, avail=False)
    d = decision.combine(res, W)
    assert d["composite"] == pytest.approx(50) and "fundamental" in d["missing"] and d["coverage"] == pytest.approx(0.8)


def test_decision_conflict_is_no_trade():
    res = {k: _mr(k, 50 if i % 2 else -50) for i, k in enumerate(W)}
    assert decision.combine(res, W)["action"] in ("No trade",) or abs(decision.combine(res, W)["composite"]) < 15


# ---------- risk
def test_position_size_risk_cash():
    acct = risk.Account(100_000, 0.5, 5, 10, 2)
    p = risk.position_size("EURUSD=X", 1.10, 1.095, acct)
    assert p["risk_cash"] == 500 and p["lots"] == pytest.approx(1.0, abs=0.01)


def test_risk_gate_rejects_poor_rr():
    acct = risk.Account(100_000, 0.5, 5, 10, 2)
    setup = {"direction": "long", "entry": 100, "stop": 99, "targets": [101], "rr": [1.0]}
    out = risk.evaluate("AAPL", setup, acct)
    assert not out["approved"] and any(c["check"] == "Reward:risk" and not c["pass"] for c in out["checks"])
