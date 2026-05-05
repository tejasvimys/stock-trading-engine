"""FastAPI application entry point."""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from routers import insights, portfolio, signals, stocks
from services.portfolio_service import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "Backend API for the Stock Trading Engine Android app. "
        "Provides stock screening, buy/sell signals, portfolio management, "
        "and AI-driven market insights."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS – allow the Android emulator (10.0.2.2) and localhost
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.allowed_origins == "*" else settings.allowed_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(stocks.router)
app.include_router(signals.router)
app.include_router(portfolio.router)
app.include_router(insights.router)


@app.on_event("startup")
async def startup_event():
    logger.info("Initialising database…")
    await init_db()
    logger.info("Stock Trading Engine API is ready.")


@app.get("/", tags=["Health"])
async def root():
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
