"""Modelos de base de datos (SQLAlchemy 2.0)."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import Date, DateTime, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Keyword(Base):
    """Término de la watchlist (producto, marca o nicho)."""

    __tablename__ = "keywords"

    id: Mapped[int] = mapped_column(primary_key=True)
    term: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=lambda: dt.datetime.now(dt.timezone.utc)
    )
    observations: Mapped[list["Observation"]] = relationship(
        back_populates="keyword", cascade="all, delete-orphan"
    )


class Observation(Base):
    """Valor de interés de un término en una fecha y fuente concretas."""

    __tablename__ = "observations"
    __table_args__ = (UniqueConstraint("keyword_id", "source", "date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    keyword_id: Mapped[int] = mapped_column(ForeignKey("keywords.id"), index=True)
    source: Mapped[str] = mapped_column(String(50), index=True)
    date: Mapped[dt.date] = mapped_column(Date, index=True)
    value: Mapped[float] = mapped_column(Float)
    keyword: Mapped[Keyword] = relationship(back_populates="observations")
