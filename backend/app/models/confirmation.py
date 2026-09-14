#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Ticket availability confirmations used by the WeCom human-in-the-loop flow."""

from datetime import datetime, timedelta
from enum import Enum as PyEnum
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base


def china_now() -> datetime:
    return datetime.utcnow() + timedelta(hours=8)


class ConfirmationStatus(str, PyEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    IGNORED = "ignored"
    EXPIRED = "expired"
    CONSUMED = "consumed"
    FAILED = "failed"


class TicketConfirmation(Base):
    __tablename__ = "ticket_confirmations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[ConfirmationStatus] = mapped_column(
        Enum(ConfirmationStatus), default=ConfirmationStatus.PENDING, index=True
    )

    train_date: Mapped[str] = mapped_column(String(20))
    train_code: Mapped[str] = mapped_column(String(30))
    seat_type: Mapped[str] = mapped_column(String(10))
    seat_name: Mapped[str] = mapped_column(String(30))
    seat_count_snapshot: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    train_secret_snapshot: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    actor_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    order_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=china_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=china_now, onupdate=china_now)

    task = relationship("Task", back_populates="confirmations")
