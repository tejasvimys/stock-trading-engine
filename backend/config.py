from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "Stock Trading Engine API"
    app_version: str = "1.0.0"
    debug: bool = False

    # Database
    database_url: str = "sqlite+aiosqlite:///./stock_trading.db"

    # API host/port
    host: str = "0.0.0.0"
    port: int = 8000

    # CORS origins (comma-separated)
    allowed_origins: str = "*"

    # Scheduler intervals (minutes)
    data_sync_interval_minutes: int = 15

    # Stock universe – default US large caps/liquid names; override via .env
    default_tickers: str = (
        "AAPL,MSFT,NVDA,AMZN,META,GOOGL,AMD,AVGO,TSLA,CRM,"
        "JPM,LLY,COST,NFLX,UBER,ADBE,PLTR,AMAT,QCOM,PANW"
    )
    defensive_tickers: str = "SH,PSQ"

    # Profit target (fraction)
    profit_target: float = 0.10
    default_account_size: float = 5000.0
    default_daily_profit_target: float = 20.0
    max_positions: int = 5
    risk_per_trade_pct: float = 0.01
    min_hold_days: int = 3
    max_hold_days: int = 15
    backtest_lookback_bars: int = 120
    paper_learning_rate: float = 0.15
    paper_auto_trading_enabled: bool = False
    paper_auto_cycle_interval_minutes: int = 15
    history_cache_dir: str = ".cache/history"
    history_fetch_timeout_seconds: float = 3.0
    history_fetch_concurrency: int = 6
    signal_generation_timeout_seconds: float = 6.0
    alpha_vantage_api_key: str = ""
    fmp_api_key: str = ""
    finnhub_api_key: str = ""
    provider_timeout_seconds: float = 10.0


settings = Settings()
