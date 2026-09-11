from __future__ import annotations

import datetime as dt
import json
from typing import Any

from sqlalchemy import String, Text, DateTime, Float, ForeignKey, create_engine
from sqlalchemy.orm import (DeclarativeBase, Mapped, mapped_column,
                            relationship, sessionmaker)

from .config import settings


class Base(DeclarativeBase):
    pass


class JSONMixin:
    """SQLite has no JSON type worth relying on; store text, parse on read."""

    @staticmethod
    def _load(raw: str | None) -> Any:
        return json.loads(raw) if raw else None


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Song(Base, JSONMixin):
    __tablename__ = "songs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    # Directory holding this song's stems.
    folder: Mapped[str] = mapped_column(Text)
    # JSON: {"stem name": "relative/path.wav", ...}
    stems_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)

    tempo: Mapped[float | None] = mapped_column(Float, nullable=True)
    key: Mapped[str | None] = mapped_column(String(32), nullable=True)
    duration: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Path to the cached AnalysisResult JSON, when analysed.
    analysis_path: Mapped[str | None] = mapped_column(Text, nullable=True)

    @property
    def stems(self) -> dict:
        return self._load(self.stems_json) or {}


class SetList(Base):
    __tablename__ = "setlists"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    items: Mapped[list["SetListItem"]] = relationship(
        back_populates="setlist", cascade="all, delete-orphan",
        order_by="SetListItem.position",
    )


class SetListItem(Base):
    __tablename__ = "setlist_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    setlist_id: Mapped[str] = mapped_column(ForeignKey("setlists.id"))
    song_id: Mapped[str] = mapped_column(ForeignKey("songs.id"))
    position: Mapped[int] = mapped_column(default=0)
    # Optional per-performance overrides, JSON.
    overrides_json: Mapped[str] = mapped_column(Text, default="{}")

    setlist: Mapped[SetList] = relationship(back_populates="items")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))           # analyze | build
    state: Mapped[str] = mapped_column(String(16), default="queued")
    target_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    message: Mapped[str] = mapped_column(Text, default="")
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(engine)


def session():
    return SessionLocal()
