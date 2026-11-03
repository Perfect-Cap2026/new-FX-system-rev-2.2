"""FRED (St. Louis Fed). Uses the official API when FRED_API_KEY is set, the public CSV export otherwise."""
import io
import logging

import httpx
import pandas as pd

from app.core.logging import PROVIDER_CALLS
from app.providers.base import MacroProvider

log = logging.getLogger(__name__)


class FredProvider(MacroProvider):
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key
        self.client = httpx.Client(timeout=20, headers={"User-Agent": "fip/1.0"})

    def get_series(self, series_id: str) -> pd.Series:
        try:
            if self.api_key:
                r = self.client.get(
                    "https://api.stlouisfed.org/fred/series/observations",
                    params={"series_id": series_id, "api_key": self.api_key, "file_type": "json",
                            "observation_start": "2005-01-01"},
                )
                r.raise_for_status()
                obs = r.json()["observations"]
                s = pd.Series({o["date"]: o["value"] for o in obs})
            else:
                r = self.client.get("https://fred.stlouisfed.org/graph/fredgraph.csv",
                                    params={"id": series_id, "cosd": "2005-01-01"})
                r.raise_for_status()
                df = pd.read_csv(io.StringIO(r.text))
                s = pd.Series(df.iloc[:, 1].values, index=df.iloc[:, 0].values)
            PROVIDER_CALLS.labels("fred", series_id, "ok").inc()
        except Exception:
            PROVIDER_CALLS.labels("fred", series_id, "error").inc()
            log.warning(f"FRED fetch failed for {series_id}")
            return pd.Series(dtype=float)
        s.index = pd.to_datetime(s.index)
        return pd.to_numeric(s, errors="coerce").dropna().sort_index()
