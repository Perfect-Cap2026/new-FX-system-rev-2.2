"""Yahoo Finance via yfinance — free, no key, delayed data. Fine for swing/daily analysis."""
import logging
import time

import pandas as pd

from app.core.logging import PROVIDER_CALLS
from app.providers.base import MarketDataProvider

log = logging.getLogger(__name__)

_PERIOD = {"1h": ("60d", "1h"), "1d": ("5y", "1d"), "1wk": ("10y", "1wk")}


class YahooProvider(MarketDataProvider):
    name = "yahoo"

    def __init__(self):
        import yfinance as yf

        self._yf = yf

    def get_bars(self, symbol: str, timeframe: str = "1d", limit: int = 500) -> pd.DataFrame:
        period, interval = _PERIOD[timeframe]
        t0 = time.perf_counter()
        try:
            df = self._yf.Ticker(symbol).history(period=period, interval=interval, auto_adjust=True)
            PROVIDER_CALLS.labels(self.name, "bars", "ok").inc()
        except Exception:
            PROVIDER_CALLS.labels(self.name, "bars", "error").inc()
            log.exception("yahoo bars failed", extra={"symbol": symbol})
            return pd.DataFrame()
        log.info("yahoo bars", extra={"symbol": symbol, "ms": round((time.perf_counter() - t0) * 1000)})
        if df is None or df.empty:
            return pd.DataFrame()
        df = df.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]].dropna(subset=["close"])
        df.index = pd.to_datetime(df.index, utc=True)
        return df.tail(limit)

    def get_fundamentals(self, symbol: str) -> dict:
        try:
            info = self._yf.Ticker(symbol).info or {}
            PROVIDER_CALLS.labels(self.name, "fundamentals", "ok").inc()
        except Exception:
            PROVIDER_CALLS.labels(self.name, "fundamentals", "error").inc()
            return {}
        keys = [
            "shortName", "sector", "industry", "marketCap", "currentPrice", "revenueGrowth",
            "earningsGrowth", "grossMargins", "operatingMargins", "profitMargins", "returnOnEquity",
            "debtToEquity", "freeCashflow", "trailingPE", "forwardPE", "pegRatio", "priceToBook",
            "enterpriseToEbitda", "ebitda", "totalRevenue", "netIncomeToCommon", "trailingEps",
            "forwardEps", "recommendationMean", "numberOfAnalystOpinions", "targetMeanPrice",
        ]
        return {k: info.get(k) for k in keys if info.get(k) is not None}

    def get_news(self, symbol: str) -> list[dict]:
        try:
            items = self._yf.Ticker(symbol).news or []
            PROVIDER_CALLS.labels(self.name, "news", "ok").inc()
        except Exception:
            PROVIDER_CALLS.labels(self.name, "news", "error").inc()
            return []
        out = []
        for it in items[:25]:
            c = it.get("content", it)  # yfinance changed shape in 0.2.5x
            title = c.get("title")
            if not title:
                continue
            url = (c.get("canonicalUrl") or {}).get("url") if isinstance(c.get("canonicalUrl"), dict) else c.get("link")
            out.append({
                "title": title,
                "summary": c.get("summary") or "",
                "publisher": (c.get("provider") or {}).get("displayName") if isinstance(c.get("provider"), dict) else c.get("publisher"),
                "published": c.get("pubDate") or c.get("providerPublishTime"),
                "url": url,
            })
        return out
