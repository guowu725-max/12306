#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Daily APScheduler runner for WeCom-confirmed ticket monitoring."""

import asyncio
import json
import logging
from datetime import timedelta
from typing import Optional

from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from ..core.config import get_settings
from ..core.database import AsyncSessionLocal
from ..models.task import Task, TaskLog, TaskStatus
from ..models.user import User
from ..services.confirmation_domain import (
    china_now,
    parse_daily_start_time,
    resolve_train_date,
)
from ..services.query_service import QueryService
from ..services.ticket_confirmation_service import (
    get_ticket_confirmation_service,
    is_seat_available,
    read_seat,
)
from ..services.wecom_confirmation import get_wecom_confirmation_bot

logger = logging.getLogger(__name__)
settings = get_settings()


def daily_job_id(task_id: int) -> str:
    return f"wecom_daily_{task_id}"


def scan_job_id(task_id: int) -> str:
    return f"wecom_scan_{task_id}"


def _time_range(task: Task):
    if not task.start_time_range:
        return None
    parts = task.start_time_range.split("-", 1)
    if len(parts) != 2:
        return None
    return parts[0].strip(), parts[1].strip()


class ConfirmationRunner:
    def __init__(self):
        self.scheduler = AsyncIOScheduler(
            jobstores={"default": MemoryJobStore()},
            executors={"default": AsyncIOExecutor()},
            job_defaults={"coalesce": True, "max_instances": 1},
            timezone=settings.SCHEDULER_TIMEZONE,
        )
        self.confirmation_service = get_ticket_confirmation_service()
        self.bot = get_wecom_confirmation_bot()
        self.confirmation_service.set_order_success_handler(self.stop_after_success)

    def start(self) -> None:
        if self.scheduler.running:
            return
        self.scheduler.start()
        self.scheduler.add_job(
            self.reload_tasks,
            "interval",
            seconds=60,
            id="wecom_reload_daily_tasks",
            replace_existing=True,
        )
        asyncio.create_task(self.reload_tasks())

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    async def reload_tasks(self) -> None:
        """Synchronize cron jobs with persisted active daily tasks."""
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Task).where(Task.schedule_mode == "daily"))
            tasks = result.scalars().all()

        active_ids = set()
        for task in tasks:
            if task.status in {TaskStatus.PAUSED, TaskStatus.CANCELLED}:
                continue
            if not task.daily_start_time or not task.confirmation_required:
                continue
            try:
                hour, minute = parse_daily_start_time(task.daily_start_time)
            except ValueError:
                logger.warning("任务 %s 的每日时间无效: %s", task.id, task.daily_start_time)
                continue
            active_ids.add(task.id)
            self.scheduler.add_job(
                self.run_daily_task,
                "cron",
                hour=hour,
                minute=minute,
                id=daily_job_id(task.id),
                args=[task.id],
                replace_existing=True,
                misfire_grace_time=300,
            )

        for job in self.scheduler.get_jobs():
            if not job.id.startswith("wecom_daily_"):
                continue
            try:
                task_id = int(job.id.rsplit("_", 1)[1])
            except ValueError:
                continue
            if task_id not in active_ids:
                self.scheduler.remove_job(job.id)

    async def run_daily_task(self, task_id: int) -> None:
        now = china_now()
        today = now.date().isoformat()
        async with AsyncSessionLocal() as db:
            task = await db.get(Task, task_id)
            if not task or task.schedule_mode != "daily":
                return
            if task.status in {TaskStatus.PAUSED, TaskStatus.CANCELLED}:
                return
            if task.last_daily_success_date == today:
                return
            if task.last_daily_run_date == today and self.scheduler.get_job(scan_job_id(task_id)):
                return
            if not self.bot.enabled:
                db.add(TaskLog(
                    task_id=task.id,
                    level="error",
                    message="企业微信智能机器人未完整配置，今日任务未启动",
                ))
                await db.commit()
                return
            try:
                effective_date = resolve_train_date(
                    task.train_date,
                    task.date_strategy,
                    task.date_offset_days,
                    now=now,
                )
            except ValueError as exc:
                db.add(TaskLog(task_id=task.id, level="error", message=str(exc)))
                await db.commit()
                return

            task.last_daily_run_date = today
            task.status = TaskStatus.RUNNING
            task.retry_count = 0
            task.started_at = now
            task.finished_at = None
            db.add(TaskLog(
                task_id=task.id,
                level="info",
                message=f"每日微信确认任务启动，目标日期: {effective_date}",
            ))
            await db.commit()
            interval = max(task.query_interval, settings.MIN_QUERY_INTERVAL)

        self.scheduler.add_job(
            self.scan_task,
            "interval",
            seconds=interval,
            id=scan_job_id(task_id),
            args=[task_id, effective_date],
            replace_existing=True,
        )
        asyncio.create_task(self.scan_task(task_id, effective_date))

    async def scan_task(self, task_id: int, effective_date: str) -> None:
        async with AsyncSessionLocal() as db:
            task = await db.get(Task, task_id)
            if not task or task.status != TaskStatus.RUNNING:
                await self.stop_scan(task_id)
                return
            if task.max_retry_count > 0 and task.retry_count >= task.max_retry_count:
                task.status = TaskStatus.PENDING
                task.finished_at = china_now()
                db.add(TaskLog(
                    task_id=task.id,
                    level="warning",
                    message="今日监控达到最大查询次数，等待下一次每日计划",
                ))
                await db.commit()
                await self.stop_scan(task_id)
                return
            task.retry_count += 1
            await db.commit()

            user = await db.get(User, task.user_id)
            if not user or not user.session_data:
                task.status = TaskStatus.PENDING
                db.add(TaskLog(task_id=task.id, level="error", message="12306 登录会话不存在"))
                await db.commit()
                await self.stop_scan(task_id)
                await self.bot.send_text("12306 登录已失效，请重新登录。")
                return

            try:
                session_data = json.loads(user.session_data)
                cookies = session_data.get("cookies", session_data)
            except Exception:
                cookies = {}

            train_codes = set(task.train_codes.split(",")) if task.train_codes else None
            train_types = task.train_types.split(",") if task.train_types else None
            seat_types = task.seat_types.split(",") if task.seat_types else ["O"]

        query_service = QueryService(cookies)
        try:
            trains, error = await query_service.query(
                from_station=task.from_station,
                to_station=task.to_station,
                train_date=effective_date,
                train_types=train_types,
                start_time_range=_time_range(task),
                only_has_ticket=False,
            )
            if error:
                await self._log(task_id, "warning", f"查票失败: {error}")
                return
            if train_codes:
                trains = [train for train in trains if train.train_code in train_codes]

            for train in trains:
                if not train.secret_str:
                    continue
                for seat_type in seat_types:
                    seat_name, seat_count = read_seat(train, seat_type)
                    if not is_seat_available(seat_count):
                        continue
                    try:
                        created = await self.confirmation_service.create_pending_confirmation(
                            task=task,
                            train=train,
                            train_date=effective_date,
                            seat_type=seat_type,
                            seat_name=seat_name,
                            seat_count=seat_count,
                        )
                        if created:
                            await self._log(
                                task_id,
                                "info",
                                f"发现余票并发送企业微信确认: {train.train_code} {seat_name}({seat_count})",
                            )
                            # Send one decision at a time. The pending record
                            # suppresses subsequent scans for this candidate.
                            return
                    except Exception as exc:
                        await self._log(task_id, "error", f"发送企业微信确认失败: {exc}")
                        return
        finally:
            await query_service.close()

    async def stop_scan(self, task_id: int) -> None:
        job = self.scheduler.get_job(scan_job_id(task_id))
        if job:
            self.scheduler.remove_job(job.id)

    async def stop_after_success(self, task_id: int) -> None:
        await self.stop_scan(task_id)
        async with AsyncSessionLocal() as db:
            task = await db.get(Task, task_id)
            if task and task.schedule_mode == "daily":
                task.status = TaskStatus.PENDING
                task.finished_at = china_now()
                await db.commit()

    async def pause_task(self, task_id: int) -> None:
        await self.stop_scan(task_id)
        daily_job = self.scheduler.get_job(daily_job_id(task_id))
        if daily_job:
            self.scheduler.remove_job(daily_job.id)

    async def register_task(self, task_id: int) -> None:
        await self.reload_tasks()

    async def _log(self, task_id: int, level: str, message: str) -> None:
        async with AsyncSessionLocal() as db:
            db.add(TaskLog(task_id=task_id, level=level, message=message))
            await db.commit()


_runner: Optional[ConfirmationRunner] = None


def get_confirmation_runner() -> ConfirmationRunner:
    global _runner
    if _runner is None:
        _runner = ConfirmationRunner()
    return _runner
