"""Deterministic offline data. Used by tests and DATA_PROVIDER=synthetic demos. Not real prices."""
import hashlib

import numpy as np
import pandas as pd

from app.providers.base import MacroProvider, MarketDataProvider, asset_class

_FREQ = {"1h": "h", "1d": "B", "1wk": "W-FRI"}
_BASE = {"forex": 1.1, "commodity": 2000.0, "index": 5000.0, "crypto": 60000.0, "stock": 150.0}


def _seed(*parts: str) -> int:
    return int(hashlib.sha256("|".join(parts).encode()).hexdigest()[:8], 16)


def make_ohlcv(n: int, start: float, drift: float, vol: float, seed: int, freq: str = "B",
               end: str = "2026-10-30") -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rets = rng.normal(drift, vol, n)
    close = start * np.exp(np.cumsum(rets))
    open_ = np.r_[start, close[:-1]] * (1 + rng.normal(0, vol / 4, n))
    span = np.abs(rng.normal(0, vol, n)) * close
    high = np.maximum(open_, close) + span * 0.6
    low = np.minimum(open_, close) - span * 0.6
    volume = rng.lognormal(13, 0.4, n)
    idx = pd.date_range(end=end, periods=n, freq=freq, tz="UTC")
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume}, index=idx)


class SyntheticProvider(MarketDataProvider):
    name = "synthetic"

    def get_bars(self, symbol: str, timeframe: str = "1d", limit: int = 500) -> pd.DataFrame:
        s = _seed(symbol, timeframe)
        drift = ((s % 7) - 3) * 0.0003
        base = _BASE[asset_class(symbol)]
        return make_ohlcv(limit, base, drift, 0.01, s, _FREQ[timeframe])

    def get_fundamentals(self, symbol: str) -> dict:
        if asset_class(symbol) != "stock":
            return {}
        r = np.random.default_rng(_seed(symbol, "f"))
        return {
            "shortName": symbol, "sector": "Technology", "revenueGrowth": r.uniform(-0.05, 0.3),
            "earningsGrowth": r.uniform(-0.1, 0.4), "grossMargins": r.uniform(0.3, 0.7),
            "operatingMargins": r.uniform(0.05, 0.35), "profitMargins": r.uniform(0.03, 0.3),
            "returnOnEquity": r.uniform(0.05, 0.4), "debtToEquity": r.uniform(10, 150),
            "forwardPE": r.uniform(12, 40), "trailingPE": r.uniform(14, 45), "pegRatio": r.uniform(0.8, 3),
            "freeCashflow": 5e9, "marketCap": 2e11, "recommendationMean": r.uniform(1.6, 3.2),
            "numberOfAnalystOpinions": 30,
        }

    def get_news(self, symbol: str) -> list[dict]:
        return [
            {"title": f"{symbol} rallies as demand beats expectations", "summary": "", "publisher": "Synthetic"},
            {"title": f"Analysts upgrade outlook for {symbol} on strong growth", "summary": "", "publisher": "Synthetic"},
            {"title": f"{symbol} faces risk from slowing global economy", "summary": "", "publisher": "Synthetic"},
        ]


class SyntheticMacro(MacroProvider):
    def get_series(self, series_id: str) -> pd.Series:
        rng = np.random.default_rng(_seed(series_id))
        idx = pd.date_range(end="2026-10-01", periods=240, freq="MS")
        levels = {"DGS10": 4.2, "DGS2": 3.9, "DGS3MO": 3.8, "DFF": 3.9, "UNRATE": 4.3, "T10YIE": 2.3,
                  "BAMLH0A0HYM2": 3.2, "SAHMREALTIME": 0.2, "RRPONTSYD": 100.0}
        if series_id in levels:
            return pd.Series(levels[series_id] + np.cumsum(rng.normal(0, 0.03, len(idx))), index=idx)
        return pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0022, 0.002, len(idx)))), index=idx)
