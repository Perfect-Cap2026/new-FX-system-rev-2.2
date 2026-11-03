from functools import lru_cache

import pandas as pd

from app.core.cache import cached
from app.core.config import get_settings
from app.providers.base import MacroProvider, MarketDataProvider

_TTL = {"1h": 300, "1d": 900, "1wk": 3600}


@lru_cache
def market() -> MarketDataProvider:
    if get_settings().data_provider == "synthetic":
        from app.providers.synthetic import SyntheticProvider
        return SyntheticProvider()
    from app.providers.yahoo import YahooProvider
    return YahooProvider()


@lru_cache
def macro() -> MacroProvider:
    s = get_settings()
    if s.data_provider == "synthetic":
        from app.providers.synthetic import SyntheticMacro
        return SyntheticMacro()
    from app.providers.fred import FredProvider
    return FredProvider(s.fred_api_key)


def bars(symbol: str, tf: str = "1d", limit: int = 500) -> pd.DataFrame:
    df = cached(f"bars:{symbol}:{tf}", _TTL[tf], lambda: market().get_bars(symbol, tf, 1000))
    return df.tail(limit) if df is not None else pd.DataFrame()


def fundamentals(symbol: str) -> dict:
    return cached(f"fund:{symbol}", 6 * 3600, lambda: market().get_fundamentals(symbol)) or {}


def news(symbol: str) -> list[dict]:
    return cached(f"news:{symbol}", 600, lambda: market().get_news(symbol)) or []


def fred(series_id: str) -> pd.Series:
    s = cached(f"fred:{series_id}", 6 * 3600, lambda: macro().get_series(series_id))
    return s if s is not None else pd.Series(dtype=float)
