from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SECRET = "dev-only-insecure-secret-change-me-in-production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    env: str = "development"
    app_name: str = "Financial Intelligence Platform"
    api_prefix: str = "/api/v1"

    database_url: str = "sqlite:///./fip.db"
    redis_url: str | None = None

    jwt_secret: str = DEFAULT_SECRET
    jwt_expire_minutes: int = 60
    cors_origins: str = "http://localhost:3000"

    # "yahoo" (live, free) or "synthetic" (offline, deterministic — tests/demo)
    data_provider: str = "yahoo"
    fred_api_key: str | None = None  # optional; keyless CSV endpoint is used otherwise
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-5-5"

    default_watchlist: str = "EURUSD=X,GBPUSD=X,USDJPY=X,GC=F,CL=F,^GSPC,^NDX,BTC-USD,AAPL,NVDA"

    # Decision weights (must sum to 1)
    w_macro: float = 0.25
    w_fundamental: float = 0.20
    w_institutional: float = 0.20
    w_technical: float = 0.15
    w_sentiment: float = 0.10
    w_intermarket: float = 0.10

    # Prop-firm risk defaults
    account_equity: float = 100_000
    risk_per_trade_pct: float = 0.5
    max_daily_loss_pct: float = 5.0
    max_total_drawdown_pct: float = 10.0
    min_rr: float = 2.0

    @property
    def weights(self) -> dict[str, float]:
        return {
            "macro": self.w_macro,
            "fundamental": self.w_fundamental,
            "institutional": self.w_institutional,
            "technical": self.w_technical,
            "sentiment": self.w_sentiment,
            "intermarket": self.w_intermarket,
        }

    @property
    def watchlist(self) -> list[str]:
        return [s.strip() for s in self.default_watchlist.split(",") if s.strip()]


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if s.env == "production" and s.jwt_secret == DEFAULT_SECRET:
        raise RuntimeError("JWT_SECRET must be set in production")
    return s
