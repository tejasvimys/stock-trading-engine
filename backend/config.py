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

    # Stock universe – default NSE/BSE large caps; override via .env
    default_tickers: str = (
        "RELIANCE.NS,TCS.NS,INFY.NS,HDFCBANK.NS,ICICIBANK.NS,"
        "HINDUNILVR.NS,BAJFINANCE.NS,SBIN.NS,BHARTIARTL.NS,KOTAKBANK.NS,"
        "WIPRO.NS,AXISBANK.NS,LT.NS,HCLTECH.NS,ADANIENT.NS,"
        "MARUTI.NS,SUNPHARMA.NS,TITAN.NS,NTPC.NS,ONGC.NS"
    )

    # Profit target (fraction)
    profit_target: float = 0.10


settings = Settings()
