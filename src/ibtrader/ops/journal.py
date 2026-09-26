from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, DateTime, Float, Integer, MetaData, String, Table, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.sql import insert

metadata = MetaData()

trades_table = Table(
    "trades",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("timestamp", DateTime, default=datetime.utcnow, index=True),
    Column("symbol", String, nullable=False, index=True),
    Column("side", String, nullable=False),
    Column("quantity", Integer, nullable=False),
    Column("price", Float, nullable=False),
    Column("commission", Float, default=0.0),
    Column("client_tag", String, nullable=True),
    Column("exit_reason", String, nullable=True),
)

decisions_table = Table(
    "decisions",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("timestamp", DateTime, default=datetime.utcnow, index=True),
    Column("symbol", String, nullable=False, index=True),
    Column("action", String, nullable=False),  # BUY/SELL/HOLD/WATCH/NO_TRADE
    Column("score", Float, nullable=True),
    Column("confidence", Float, nullable=True),
    Column("position_size", Float, nullable=True),
    Column("reason", String, nullable=True),
    Column("regime", String, nullable=True),  # JSON-encoded short dict
    Column("source", String, nullable=True),  # JSON metadatos (fuentes/metodologías)
)


def get_engine(db_path: str) -> Engine:
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    metadata.create_all(engine)
    return engine


def record_trade(
    engine: Engine,
    symbol: str,
    side: str,
    quantity: int,
    price: float,
    commission: float = 0.0,
    client_tag: Optional[str] = None,
    exit_reason: Optional[str] = None,
) -> None:
    with engine.begin() as conn:
        stmt = insert(trades_table).values(
            timestamp=datetime.now(timezone.utc),
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            commission=commission,
            client_tag=client_tag,
            exit_reason=exit_reason,
        )
        conn.execute(stmt)


def record_decision(
    engine: Engine,
    symbol: str,
    action: str,
    score: float,
    confidence: float,
    position_size: float,
    reason: str,
    regime_json: str,
    source_json: str,
) -> None:
    with engine.begin() as conn:
        stmt = insert(decisions_table).values(
            timestamp=datetime.now(timezone.utc),
            symbol=symbol,
            action=action,
            score=score,
            confidence=confidence,
            position_size=position_size,
            reason=reason,
            regime=regime_json,
            source=source_json,
        )
        conn.execute(stmt)

