# Stock Trading Engine

A full-stack stock screening and trading-signal system consisting of:

| Component | Technology |
|-----------|-----------|
| **Android App** | Kotlin + Jetpack Compose |
| **Backend API** | Python + FastAPI |
| **Data Source** | Yahoo Finance (`yfinance`) |
| **Database** | SQLite (async via SQLAlchemy) |

---

## Features

### Android App
| Screen | Description |
|--------|-------------|
| **Stock Screener** | Filter stocks by RSI, MACD direction, Bollinger Band position, and volume. Sort results by any indicator. |
| **Trade Signals** | Swing-trade signals with target/stop, account-aware sizing, projected profit/day, paper-trading evidence, confidence, and rationale. |
| **Portfolio** | Add/remove holdings, track unrealised P&L, current value vs invested value, and portfolio weights. |
| **Market Insights** | Daily/weekly AI-driven summaries: top gainers/losers, sector performance, key observations, and recommended actions. |

### Backend API
| Endpoint | Description |
|----------|-------------|
| `GET /stocks/screen` | Screen stocks with technical-indicator filters |
| `GET /signals` | Generate buy/sell swing signals with account-aware sizing and backtest evidence |
| `GET /portfolio` | Retrieve portfolio summary with live prices |
| `GET /paper/summary` | Retrieve local paper portfolio, learning weights, and target progress |
| `POST /paper/run-cycle` | Run one end-of-day long-only paper-trading cycle |
| `POST /paper/replay` | Replay recent market days locally for learning |
| `GET /paper/trades` | Review simulated buys/sells and realised P&L |
| `GET /paper/snapshots` | Review the paper equity curve over time |
| `GET /paper/strategy` | Inspect current adaptive scoring weights |
| `POST /portfolio/holdings` | Add or average-in a holding |
| `DELETE /portfolio/holdings/{symbol}` | Remove a holding |
| `GET /insights` | Get daily or weekly market insights |
| `GET /health` | Health check |
| `GET /docs` | Interactive Swagger UI |

---

## Repository Layout

```
stock-trading-engine/
├── backend/                   # Python FastAPI backend
│   ├── main.py                # App entry point
│   ├── config.py              # Settings (pydantic-settings, .env support)
│   ├── models.py              # Pydantic request/response models
│   ├── requirements.txt       # Python dependencies
│   ├── .env.example           # Sample environment file
│   ├── test_backend.py        # Unit tests
│   ├── routers/
│   │   ├── stocks.py          # /stocks/* endpoints
│   │   ├── signals.py         # /signals endpoint
│   │   ├── portfolio.py       # /portfolio/* endpoints
│   │   └── insights.py        # /insights endpoint
│   └── services/
│       ├── data_fetcher.py    # yfinance wrapper with in-memory cache
│       ├── screener.py        # Technical indicator computation & filtering
│       ├── signal_engine.py   # Buy/sell signal generation logic
│       ├── portfolio_service.py # SQLite-backed portfolio CRUD
│       └── insights_service.py  # Market insights narrative generation
└── android/                   # Android application (Kotlin + Jetpack Compose)
    ├── settings.gradle.kts
    ├── build.gradle.kts
    ├── gradle.properties
    ├── gradle/
    │   ├── libs.versions.toml # Version catalog
    │   └── wrapper/
    └── app/
        ├── build.gradle.kts
        ├── proguard-rules.pro
        └── src/main/
            ├── AndroidManifest.xml
            └── java/com/stocktrading/
                ├── MainActivity.kt
                ├── StockTradingApp.kt
                ├── data/
                │   ├── api/           # Retrofit API service & models
                │   └── repository/    # Data repositories
                ├── ui/
                │   ├── navigation/    # Bottom-nav host
                │   ├── screens/       # Screener, Signals, Portfolio, Insights
                │   └── theme/         # Material3 theme, colours, typography
                └── utils/Constants.kt
```

---

## Backend Setup

### Prerequisites
- Python 3.10 or later
- pip

### Installation

```bash
cd backend

# (Optional) create a virtual environment
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Configuration

Copy the sample environment file and edit as needed:

```bash
cp .env.example .env
# Edit .env to customise port, tickers, profit target, etc.
```

Key settings:

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `8000` | TCP port to listen on |
| `DEFAULT_TICKERS` | 20 liquid US equities | Comma-separated primary watchlist symbols |
| `DEFENSIVE_TICKERS` | `SH,PSQ` | Long-only inverse ETFs the engine can use during bearish conditions |
| `PROFIT_TARGET` | `0.10` | Signal profit target (10%) |
| `DEFAULT_ACCOUNT_SIZE` | `5000` | Default account size in USD |
| `DEFAULT_DAILY_PROFIT_TARGET` | `20` | Daily profit target used by the planner |
| `MAX_POSITIONS` | `5` | Maximum concurrent swing positions |
| `RISK_PER_TRADE_PCT` | `0.01` | Max account risk per trade |
| `PAPER_LEARNING_RATE` | `0.15` | How quickly the adaptive paper strategy reweights itself |
| `HISTORY_CACHE_DIR` | `.cache/history` | Local on-disk history cache used to survive provider outages and backend restarts |
| `HISTORY_FETCH_TIMEOUT_SECONDS` | `3` | Per-symbol timeout for history fetches so stalled market-data requests fail fast |
| `HISTORY_FETCH_CONCURRENCY` | `6` | Maximum concurrent price-history fetches |
| `SIGNAL_GENERATION_TIMEOUT_SECONDS` | `6` | Total time budget for filling uncached signal histories before the API falls back to cached-only results |
| `ALPHA_VANTAGE_API_KEY` | empty | Optional Alpha Vantage key used as a rate-limited daily-history fallback |
| `FMP_API_KEY` | empty | Financial Modeling Prep API key for provider-backed fundamentals/news/targets |
| `FINNHUB_API_KEY` | empty | Finnhub API key for provider-backed financials/recommendations/news |
| `PROVIDER_TIMEOUT_SECONDS` | `10` | Timeout for external provider API calls |
| `ALLOWED_ORIGINS` | `*` | CORS origins |

### Running the API

```bash
# Development (auto-reload)
uvicorn main:app --reload --port 8000

# Production
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 2
```

The Swagger UI will be available at **http://localhost:8000/docs**.

### Running Backend Tests

```bash
cd backend
pip install pytest
python -m pytest test_backend.py -v
```

### Hosting on Your Own Domain

1. Point your domain's DNS A-record to your box's public IP.
2. Set up a reverse proxy (nginx/Caddy) to forward traffic from port 443 → `localhost:8000`.
3. Obtain a TLS certificate (Let's Encrypt / Certbot).
4. Update `ALLOWED_ORIGINS` in `.env` to your app's package identifier or `*`.
5. In the Android app's `app/build.gradle.kts`, update the `release` build-config field:
   ```kotlin
   buildConfigField("String", "API_BASE_URL", "\"https://api.yourdomain.com/\"")
   ```

---

## Android App Setup

### Prerequisites
- Android Studio Hedgehog (2023.1.1) or later
- JDK 17
- Android SDK API 26+

### Opening the Project

1. Launch Android Studio.
2. Select **Open** and navigate to the `android/` directory.
3. Wait for Gradle sync to complete.

### Configuring the API URL

| Build Type | Default URL | When to use |
|------------|-------------|-------------|
| `debug` | `http://10.0.2.2:8000/` | Android Emulator → host machine |
| `release` | `https://api.yourdomain.com/` | Your hosted domain |

To point debug builds at a physical device on the same network, edit `app/build.gradle.kts`:

```kotlin
buildConfigField("String", "API_BASE_URL", "\"http://192.168.x.x:8000/\"")
```

### Building & Running

```
Run → Run 'app'   (or Shift+F10)
```

For a release APK:

```
Build → Generate Signed Bundle / APK
```

---

## Technical Indicators Used

| Indicator | Parameters | Signal logic |
|-----------|-----------|-------------|
| RSI | Window 14 | Bullish swing zone, pullback, and exhaustion checks |
| MACD | 12/26/9 | Confirms bullish/bearish crossover direction |
| Bollinger Bands | 20-day, 2σ | Distinguishes healthy continuation from stretched moves |
| SMA | 20-day, 50-day | Trend regime and pullback context |
| Volume | 20-day avg | Confirms participation on breakout/pullback days |
| Momentum | 5-day / 10-day return | Rewards sustained swing direction |

Signals are ranked by a composite of signal quality, historical paper-trade results, and fit for the configured account size. BUY signals include a trade plan with recommended shares, position size, projected profit/day, and risk budget.

---

## Multi-Source Intelligence Layer

The first local-only intelligence layer uses **free/public-access data** and folds it into the swing-ranking engine. If `FMP_API_KEY` and `FINNHUB_API_KEY` are present in your local `.env`, the backend enriches the default Yahoo-based flow with provider-backed data:

| Source family | Current use in scoring |
|---|---|
| **Price/volume history** | Trend, momentum, volatility, and technical setup quality |
| **Fundamentals** | Revenue growth, earnings growth, margins, ROE, and valuation context |
| **Analyst proxies** | Recommendation key, analyst count, and median/mean target-price upside |
| **Ownership proxies** | Insider/institutional ownership percentages |
| **Events** | Upcoming earnings timing and event-risk penalty |
| **News sentiment** | Headline keyword sentiment over recent news flow |
| **Options context** | Put/call open-interest balance and implied-volatility tone |

### Provider mapping

| Provider | Current role |
|---|---|
| **Yahoo Finance** | Base price history, fallback company info, fallback options context, fallback calendar |
| **Alpha Vantage** | Rate-limited fallback for daily historical OHLCV when Yahoo/FMP are unavailable |
| **FMP** | Company profile, quote, price target consensus, stock news |
| **Finnhub** | Basic financial metrics, analyst recommendation trends, company news, insider sentiment |

Provider data is merged into a single normalized intelligence snapshot before the signal engine ranks trades.

The backend also persists fetched historical price data to a small local cache directory so paper-trading cycles can keep running after a restart even when Yahoo/FMP are temporarily rate-limiting requests.

This version is intentionally built so premium providers can be plugged in later behind the same scoring concepts. The most natural future upgrades are:

1. Broker/Wall Street research feeds
2. Historical news/sentiment archives
3. Options-flow and dark-pool providers
4. Insider transaction feeds with point-in-time history
5. Economic calendar and macro surprise data

**Important:** the engine can become more robust, but it still cannot guarantee profit. It should be treated as a decision-support and paper-trading system until its live paper results prove consistent.

---

## Architecture Overview

```
Android App (Kotlin / Jetpack Compose)
        │
        │  HTTP (Retrofit2 + OkHttp)
        ▼
FastAPI Backend (Python)
        │
        ├── yfinance  ──→  Yahoo Finance (market data)
        ├── ta        ──→  RSI, MACD, BB, SMA, EMA computation
        └── SQLite    ──→  Portfolio persistence
```

- The Android app follows **MVVM** with `ViewModel` + `StateFlow`.
- Each screen has its own ViewModel and Repository.
- The backend is fully **async** (FastAPI + aiosqlite).
- Stock data is cached in-memory for 15 minutes to avoid excessive API calls.
- The paper-trading engine runs locally, simulates long-only end-of-day trades, journals outcomes in SQLite, and adapts ranking weights from realised paper-trade results.

---

## Adding More Stocks

Edit `DEFAULT_TICKERS` in `backend/.env` using valid [yfinance](https://github.com/ranaroussi/yfinance) ticker symbols:

```env
DEFAULT_TICKERS=AAPL,MSFT,GOOGL,AMZN,NVDA
```

To let the long-only paper engine defend in weak markets, keep a small inverse-ETF sleeve in `DEFENSIVE_TICKERS`:

```env
DEFENSIVE_TICKERS=SH,PSQ
```

US stocks use plain tickers; NSE/BSE stocks use `.NS` / `.BO` suffixes (e.g. `RELIANCE.NS`).

---

## License

MIT
