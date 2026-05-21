"""Portfolio management service backed by SQLite."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

from sqlalchemy import Column, Float, Integer, String, delete, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from config import settings
from models import AddHoldingRequest, PortfolioHolding, PortfolioSummary
from services.data_fetcher import fetch_history, get_latest_price, fetch_info

logger = logging.getLogger(__name__)

engine = create_async_engine(settings.database_url, echo=False, future=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class HoldingORM(Base):
    __tablename__ = "holdings"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, unique=True, nullable=False, index=True)
    quantity = Column(Float, nullable=False)
    avg_buy_price = Column(Float, nullable=False)
    added_at = Column(String, default=lambda: datetime.utcnow().isoformat())


async def init_db() -> None:
    # Import additional services that register ORM models on the shared metadata.
    from services import paper_trading_service  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        columns = await conn.execute(text("PRAGMA table_info(paper_positions)"))
        column_names = {row[1] for row in columns.fetchall()}
        if "side" not in column_names:
            await conn.execute(text("ALTER TABLE paper_positions ADD COLUMN side VARCHAR NOT NULL DEFAULT 'LONG'"))


async def add_holding(req: AddHoldingRequest) -> PortfolioHolding:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(HoldingORM).where(HoldingORM.symbol == req.symbol.upper())
        )
        existing = result.scalar_one_or_none()
        if existing:
            # Average down/up
            total_qty = existing.quantity + req.quantity
            new_avg = (
                (existing.avg_buy_price * existing.quantity + req.avg_buy_price * req.quantity)
                / total_qty
            )
            existing.quantity = total_qty
            existing.avg_buy_price = round(new_avg, 2)
            await session.commit()
            await session.refresh(existing)
            orm_obj = existing
        else:
            orm_obj = HoldingORM(
                symbol=req.symbol.upper(),
                quantity=req.quantity,
                avg_buy_price=req.avg_buy_price,
            )
            session.add(orm_obj)
            await session.commit()
            await session.refresh(orm_obj)

    return _to_holding(orm_obj)


async def remove_holding(symbol: str) -> bool:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            delete(HoldingORM).where(HoldingORM.symbol == symbol.upper())
        )
        await session.commit()
        return result.rowcount > 0


async def get_portfolio() -> PortfolioSummary:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(HoldingORM))
        orm_list = result.scalars().all()

    holdings: List[PortfolioHolding] = []
    total_invested = 0.0
    total_current = 0.0

    for orm_obj in orm_list:
        holding = _to_holding(orm_obj)
        df = fetch_history(orm_obj.symbol, period="5d")
        info = fetch_info(orm_obj.symbol)
        price = get_latest_price(df)
        holding.name = info.get("longName") or info.get("shortName") or orm_obj.symbol
        if price:
            holding.current_price = round(price, 2)
            holding.current_value = round(price * orm_obj.quantity, 2)
            holding.invested_value = round(orm_obj.avg_buy_price * orm_obj.quantity, 2)
            holding.unrealised_pnl = round(holding.current_value - holding.invested_value, 2)
            if holding.invested_value > 0:
                holding.unrealised_pnl_pct = round(
                    holding.unrealised_pnl / holding.invested_value * 100, 2
                )
        invested = (orm_obj.avg_buy_price * orm_obj.quantity) if orm_obj.quantity else 0
        current = (price * orm_obj.quantity) if price else invested
        total_invested += invested
        total_current += current
        holdings.append(holding)

    # Compute weights
    if total_current > 0:
        for h in holdings:
            h.weight = round((h.current_value or 0) / total_current * 100, 2)

    pnl = round(total_current - total_invested, 2)
    pnl_pct = round(pnl / total_invested * 100, 2) if total_invested > 0 else 0.0

    return PortfolioSummary(
        total_invested=round(total_invested, 2),
        current_value=round(total_current, 2),
        total_pnl=pnl,
        total_pnl_pct=pnl_pct,
        holdings_count=len(holdings),
        holdings=holdings,
    )


def _to_holding(orm_obj: HoldingORM) -> PortfolioHolding:
    return PortfolioHolding(
        symbol=orm_obj.symbol,
        quantity=orm_obj.quantity,
        avg_buy_price=orm_obj.avg_buy_price,
    )
