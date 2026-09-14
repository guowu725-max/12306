#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Small idempotent compatibility migrations for existing SQLite databases."""

from sqlalchemy import text


_TASK_COLUMNS = {
    "schedule_mode": "VARCHAR(20) NOT NULL DEFAULT 'once'",
    "daily_start_time": "VARCHAR(5)",
    "date_strategy": "VARCHAR(20) NOT NULL DEFAULT 'fixed'",
    "date_offset_days": "INTEGER NOT NULL DEFAULT 0",
    "confirmation_required": "BOOLEAN NOT NULL DEFAULT 0",
    "last_daily_run_date": "VARCHAR(10)",
    "last_daily_success_date": "VARCHAR(10)",
}


async def run_compat_migrations(conn) -> None:
    """Add columns introduced after the original create_all-only schema."""
    if conn.dialect.name != "sqlite":
        return

    table_rows = await conn.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'")
    )
    if table_rows.first() is None:
        return

    result = await conn.execute(text("PRAGMA table_info(tasks)"))
    existing = {row[1] for row in result.fetchall()}

    for name, ddl in _TASK_COLUMNS.items():
        if name in existing:
            continue
        await conn.execute(text(f"ALTER TABLE tasks ADD COLUMN {name} {ddl}"))
