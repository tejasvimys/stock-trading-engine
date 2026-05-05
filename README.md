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
| **Trade Signals** | AI-style buy/sell signals targeting ≥10% profit. Shows entry price, target, stop-loss, confidence score, and rationale. |
| **Portfolio** | Add/remove holdings, track unrealised P&L, current value vs invested value, and portfolio weights. |
| **Market Insights** | Daily/weekly AI-driven summaries: top gainers/losers, sector performance, key observations, and recommended actions. |

### Backend API
| Endpoint | Description |
|----------|-------------|
| `GET /stocks/screen` | Screen stocks with technical-indicator filters |
| `GET /signals` | Generate buy/sell signals (weekly or monthly timeframe) |
| `GET /portfolio` | Retrieve portfolio summary with live prices |
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
| `DEFAULT_TICKERS` | Top 20 NSE stocks | Comma-separated yfinance symbols |
| `PROFIT_TARGET` | `0.10` | Signal profit target (10%) |
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
| RSI | Window 14 | < 35 → oversold (buy), > 65 → overbought (sell) |
| MACD | 12/26/9 | MACD > Signal → bullish; MACD < Signal → bearish |
| Bollinger Bands | 20-day, 2σ | Price < lower band → buy setup; > upper band → sell setup |
| SMA | 20-day, 50-day | Golden cross (SMA20 > SMA50) → bullish |
| Volume | 20-day avg | Volume surge (>1.5× avg) amplifies signal strength |
| Momentum | 5-day return | >2% → buy momentum; <-2% → sell pressure |

Signal confidence is computed as `signals_confirming / total_checks`. Only stocks scoring a clear majority in one direction are shown as BUY or SELL; the rest are filtered out as HOLD.

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

---

## Adding More Stocks

Edit `DEFAULT_TICKERS` in `backend/.env` using valid [yfinance](https://github.com/ranaroussi/yfinance) ticker symbols:

```env
DEFAULT_TICKERS=AAPL,MSFT,GOOGL,AMZN,NVDA
```

US stocks use plain tickers; NSE/BSE stocks use `.NS` / `.BO` suffixes (e.g. `RELIANCE.NS`).

---

## License

MIT
