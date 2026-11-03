"""Provider interface + symbol helpers. Engines never import a concrete provider."""
import re
from abc import ABC, abstractmethod

import pandas as pd

SYMBOL_RE = re.compile(r"^[A-Za-z0-9\^\.\-=]{1,20}$")

TIMEFRAMES = {"1h", "1d", "1wk"}

INTERMARKET = {
    "DXY": "DX-Y.NYB",
    "Gold": "GC=F",
    "Silver": "SI=F",
    "Oil": "CL=F",
    "US10Y": "^TNX",
    "VIX": "^VIX",
    "S&P 500": "^GSPC",
    "Nasdaq 100": "^NDX",
    "Bitcoin": "BTC-USD",
}
# Yields/levels where daily *changes* (not % returns) are the meaningful series
LEVEL_SERIES = {"^TNX", "^VIX"}

SECTORS = {
    "XLK": "Technology", "XLF": "Financials", "XLE": "Energy", "XLV": "Health Care",
    "XLI": "Industrials", "XLY": "Cons. Discretionary", "XLP": "Cons. Staples",
    "XLU": "Utilities", "XLB": "Materials", "XLRE": "Real Estate", "XLC": "Communication",
}

COMMODITIES = {"GC=F", "SI=F", "CL=F", "BZ=F", "NG=F", "HG=F", "PL=F", "ZC=F", "ZW=F", "ZS=F"}


def validate_symbol(symbol: str) -> str:
    if not SYMBOL_RE.match(symbol or ""):
        raise ValueError(f"Invalid symbol: {symbol!r}")
    return symbol.upper() if not symbol.startswith("^") else symbol


def asset_class(symbol: str) -> str:
    s = symbol.upper()
    if s.endswith("=X"):
        return "forex"
    if s in COMMODITIES:
        return "commodity"
    if s.endswith("=F"):
        return "index" if s[:2] in {"ES", "NQ", "YM", "RT"} else "commodity"
    if s.startswith("^") or s == "DX-Y.NYB":
        return "index"
    if s.endswith("-USD") or s.endswith("-USDT"):
        return "crypto"
    return "stock"


def fx_currencies(symbol: str) -> tuple[str, str] | None:
    s = symbol.upper().replace("=X", "")
    if len(s) == 6:
        return s[:3], s[3:]
    if len(s) == 3:  # Yahoo "JPY=X" means USDJPY
        return "USD", s
    return None


class MarketDataProvider(ABC):
    name = "base"

    @abstractmethod
    def get_bars(self, symbol: str, timeframe: str = "1d", limit: int = 500) -> pd.DataFrame:
        """Columns open, high, low, close, volume; tz-aware UTC DatetimeIndex, ascending."""

    @abstractmethod
    def get_fundamentals(self, symbol: str) -> dict: ...

    @abstractmethod
    def get_news(self, symbol: str) -> list[dict]: ...


class MacroProvider(ABC):
    @abstractmethod
    def get_series(self, series_id: str) -> pd.Series:
        """Observations indexed by date, float values, ascending."""
