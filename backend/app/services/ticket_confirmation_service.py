#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Human-in-the-loop ticket confirmation and safe order submission."""

import hashlib
import hmac
import json
import secrets
from datetime import timedelta
from typing import Awaitable, Callable, Optional

from sqlalchemy import select

from ..core.config import get_settings
from ..core.database import AsyncSessionLocal
from ..models.confirmation import ConfirmationStatus, TicketConfirmation
from ..models.task import Task, TaskLog, TaskStatus
from ..models.user import User
from .confirmation_domain import china_now, clamp_confirmation_expiry
from .order_service import OrderService
from .query_service import QueryService
from .wecom_confirmation import build_confirmation_card, get_wecom_confirmation_bot

settings = get_settings()

OrderSuccessHandler = Callable[[int], Awaitable[None]]


_SEAT_FIELDS = {
    "9": ("商务座", "business_seat"),
    "P": ("优选一等座", "premier_first"),
    "M": ("一等座", "first_seat"),
    "O": ("二等座", "second_seat"),
    "6": ("高级软卧", "advanced_soft_sleeper"),
    "4": ("软卧", "soft_sleeper"),
    "I": ("一等卧", "first_sleeper"),
    "J": ("二等卧", "second_sleeper"),
    "3": ("硬卧", "hard_sleeper"),
    "2": ("软座", "soft_seat"),
    "1": ("硬座", "hard_seat"),
}


def hash_confirmation_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def is_seat_available(value: str) -> bool:
    if value in (None, "", "--", "无", "*", "0"):
        return False
    if value == "有":
        return True
    try:
        return int(value) > 0
    except (TypeError, ValueError):
        return False


def read_seat(train, seat_type: str) -> tuple[str, str]:
    seat_name, field_name = _SEAT_FIELDS.get(seat_type, (seat_type, ""))
    return seat_name, getattr(train, field_name, "--") if field_name else "--"


def _time_range(task: Task):
    if not task.start_time_range:
        return None
    parts = task.start_time_range.split("-", 1)
    if len(parts) != 2:
        return None
    return parts[0].strip(), parts[1].strip()


class TicketConfirmationService:
    def __init__(self):
        self.bot = get_wecom_confirmation_bot()
        self._order_success_handler: Optional[OrderSuccessHandler] = None

    def set_order_success_handler(self, handler: OrderSuccessHandler) -> None:
        self._order_success_handler = handler

    async def create_pending_confirmation(
        self,
        *,
        task: Task,
        train,
        train_date: str,
        seat_type: str,
        seat_name: str,
        seat_count: str,
    ) -> Optional[TicketConfirmation]:
        """Create one pending decision per task and send its WeCom card."""
        now = china_now()
        expiry_seconds = clamp_confirmation_expiry(settings.WECOM_CONFIRM_EXPIRE_SECONDS)
        raw_token = secrets.token_urlsafe(24)

        async with AsyncSessionLocal() as db:
            # Only one live decision is allowed per task. This prevents a single
            # scan from producing several actionable cards for different trains
            # or seats and makes the human-in-the-loop flow unambiguous.
            result = await db.execute(
                select(TicketConfirmation).where(
                    TicketConfirmation.task_id == task.id,
                    TicketConfirmation.status == ConfirmationStatus.PENDING,
                )
            )
            pending = result.scalars().all()
            for item in pending:
                if item.expires_at > now:
                    return None
                item.status = ConfirmationStatus.EXPIRED

            # Short cool-down after an explicit ignore for the same candidate so
            # the next 3-second scan does not immediately push an identical card.
            recent_result = await db.execute(
                select(TicketConfirmation)
                .where(
                    TicketConfirmation.task_id == task.id,
                    TicketConfirmation.train_date == train_date,
                    TicketConfirmation.train_code == train.train_code,
                    TicketConfirmation.seat_type == seat_type,
                    TicketConfirmation.status == ConfirmationStatus.IGNORED,
                )
                .order_by(TicketConfirmation.updated_at.desc())
                .limit(1)
            )
            recent_ignored = recent_result.scalar_one_or_none()
            if recent_ignored and recent_ignored.updated_at > now - timedelta(seconds=60):
                await db.commit()
                return None

            confirmation = TicketConfirmation(
                task_id=task.id,
                token_hash=hash_confirmation_token(raw_token),
                status=ConfirmationStatus.PENDING,
                train_date=train_date,
                train_code=train.train_code,
                seat_type=seat_type,
                seat_name=seat_name,
                seat_count_snapshot=str(seat_count),
                # Never rely on stale ordering credentials. Confirmation always
                # re-runs QueryService and uses the fresh secret_str.
                train_secret_snapshot=None,
                expires_at=now + timedelta(seconds=expiry_seconds),
            )
            db.add(confirmation)
            await db.flush()
            confirmation_id = confirmation.id
            await db.commit()

        passenger_names = [
            str(item.get("passenger_name", ""))
            for item in json.loads(task.passengers or "[]")
            if item.get("passenger_name")
        ]
        card = build_confirmation_card(
            confirmation_id=confirmation_id,
            raw_token=raw_token,
            task_name=task.name,
            route=f"{task.from_station} → {task.to_station}",
            train_date=train_date,
            train_code=train.train_code,
            time_range=f"{train.start_time} - {train.arrive_time}",
            seat_name=seat_name,
            seat_count=str(seat_count),
            passenger_names=passenger_names,
            expire_seconds=expiry_seconds,
        )
        try:
            await self.bot.send_confirmation(card)
        except Exception as exc:
            async with AsyncSessionLocal() as db:
                record = await db.get(TicketConfirmation, confirmation_id)
                if record and record.status == ConfirmationStatus.PENDING:
                    record.status = ConfirmationStatus.FAILED
                    record.details = f"企业微信卡片发送失败: {exc}"
                    await db.commit()
            raise
        return confirmation

    async def handle_action(
        self,
        action: str,
        confirmation_id: int,
        raw_token: str,
        actor_id: str,
    ) -> None:
        allowed = settings.WECOM_ALLOWED_USERS
        if allowed and actor_id not in allowed:
            await self.bot.send_text("该企业微信账号没有购票确认权限。")
            return

        async with AsyncSessionLocal() as db:
            confirmation = await db.get(TicketConfirmation, confirmation_id)
            if confirmation is None:
                return
            if not hmac.compare_digest(
                confirmation.token_hash, hash_confirmation_token(raw_token)
            ):
                return
            if confirmation.status != ConfirmationStatus.PENDING:
                return
            if confirmation.expires_at <= china_now():
                confirmation.status = ConfirmationStatus.EXPIRED
                await db.commit()
                await self.bot.send_text("本次余票确认已过期，系统会继续监控。")
                return
            if action == "ignore":
                confirmation.status = ConfirmationStatus.IGNORED
                confirmation.actor_id = actor_id or None
                await db.commit()
                await self.bot.send_text("已忽略本次余票，系统会继续监控。")
                return
            if action != "confirm":
                return

            # Claim before network I/O. Repeated button events see non-pending
            # state and therefore cannot start a second order attempt.
            confirmation.status = ConfirmationStatus.CONFIRMED
            confirmation.actor_id = actor_id or None
            confirmation.confirmed_at = china_now()
            await db.commit()

        await self._execute_confirmed_order(confirmation_id)

    async def _execute_confirmed_order(self, confirmation_id: int) -> None:
        async with AsyncSessionLocal() as db:
            confirmation = await db.get(TicketConfirmation, confirmation_id)
            if not confirmation or confirmation.status != ConfirmationStatus.CONFIRMED:
                return
            task = await db.get(Task, confirmation.task_id)
            if not task:
                confirmation.status = ConfirmationStatus.FAILED
                confirmation.details = "任务不存在"
                await db.commit()
                return
            user = await db.get(User, task.user_id)
            if not user or not user.session_data:
                confirmation.status = ConfirmationStatus.FAILED
                confirmation.details = "12306 登录会话不存在"
                await db.commit()
                await self.bot.send_text("12306 登录已失效，请重新登录后再启动任务。")
                return
            try:
                session_data = json.loads(user.session_data)
                cookies = session_data.get("cookies", session_data)
            except Exception:
                cookies = {}

            train_date = confirmation.train_date
            train_code = confirmation.train_code
            seat_type = confirmation.seat_type
            passenger_config = json.loads(task.passengers or "[]")
            task_id = task.id

        query_service = QueryService(cookies)
        order_service = OrderService(cookies)
        try:
            train_types = task.train_types.split(",") if task.train_types else None
            trains, error = await query_service.query(
                from_station=task.from_station,
                to_station=task.to_station,
                train_date=train_date,
                train_types=train_types,
                start_time_range=_time_range(task),
                only_has_ticket=False,
            )
            if error:
                await self._fail(confirmation_id, f"重新查票失败: {error}")
                return

            fresh_train = next((t for t in trains if t.train_code == train_code), None)
            if fresh_train is None or not fresh_train.secret_str:
                await self._fail(confirmation_id, "确认后车次已不可购买")
                return
            _, fresh_count = read_seat(fresh_train, seat_type)
            if not is_seat_available(fresh_count):
                await self._fail(confirmation_id, "确认后余票已变化，系统会继续监控")
                return

            ok, api_passengers, passenger_error = await order_service.query_passengers()
            if not ok:
                await self._fail(confirmation_id, f"刷新乘车人失败: {passenger_error}")
                return
            api_map = {(p.passenger_name, p.passenger_id_no): p for p in api_passengers}
            matched = []
            for configured in passenger_config:
                key = (
                    configured.get("passenger_name", ""),
                    configured.get("passenger_id_no", ""),
                )
                passenger = api_map.get(key)
                if passenger is None:
                    await self._fail(confirmation_id, f"找不到乘车人: {key[0]}")
                    return
                configured_type = str(configured.get("passenger_type", passenger.passenger_type))
                passenger.passenger_type = configured_type
                passenger.ticket_type = configured_type
                matched.append(passenger)

            order_result = await order_service.buy_ticket(
                fresh_train,
                fresh_train.secret_str,
                passengers=matched,
                seat_type=seat_type,
            )
            if not order_result.success:
                await self._fail(confirmation_id, order_result.message or "提交订单失败")
                return

            async with AsyncSessionLocal() as db:
                record = await db.get(TicketConfirmation, confirmation_id)
                current_task = await db.get(Task, task_id)
                if record:
                    record.status = ConfirmationStatus.CONSUMED
                    record.order_id = order_result.order_id
                    record.details = order_result.message
                if current_task:
                    current_task.order_id = order_result.order_id
                    current_task.result_message = order_result.message or "订单已提交"
                    if current_task.schedule_mode == "daily":
                        current_task.last_daily_success_date = china_now().date().isoformat()
                    else:
                        current_task.status = TaskStatus.SUCCESS
                db.add(
                    TaskLog(
                        task_id=task_id,
                        level="success",
                        message=f"微信确认后订单提交成功: {order_result.order_id}",
                    )
                )
                await db.commit()

            await self.bot.send_text(
                f"订单已提交成功。\n车次：{train_code}\n日期：{train_date}\n"
                f"订单号：{order_result.order_id}\n请尽快前往官方 12306 完成支付。"
            )
            if self._order_success_handler:
                await self._order_success_handler(task_id)
        finally:
            await query_service.close()
            await order_service.close()

    async def _fail(self, confirmation_id: int, message: str) -> None:
        async with AsyncSessionLocal() as db:
            confirmation = await db.get(TicketConfirmation, confirmation_id)
            if confirmation:
                confirmation.status = ConfirmationStatus.FAILED
                confirmation.details = message
                await db.commit()
        await self.bot.send_text(message)


_service: Optional[TicketConfirmationService] = None


def get_ticket_confirmation_service() -> TicketConfirmationService:
    global _service
    if _service is None:
        _service = TicketConfirmationService()
    return _service
