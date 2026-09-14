#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Enterprise WeChat smart-bot adapter for ticket confirmation cards."""

import asyncio
import logging
from typing import Awaitable, Callable, Optional

from ..core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

ConfirmationActionHandler = Callable[[str, int, str, str], Awaitable[None]]


def build_confirmation_card(
    *,
    confirmation_id: int,
    raw_token: str,
    task_name: str,
    route: str,
    train_date: str,
    train_code: str,
    time_range: str,
    seat_name: str,
    seat_count: str,
    passenger_names: list[str],
    expire_seconds: int,
) -> dict:
    """Build a WeCom button-interaction template card."""
    summary = (
        f"{route}\n"
        f"日期：{train_date}\n"
        f"车次：{train_code}  {time_range}\n"
        f"席别：{seat_name}（{seat_count}）\n"
        f"乘车人：{', '.join(passenger_names)}\n"
        f"请在 {expire_seconds} 秒内确认；确认后系统会重新查询余票再提交订单。"
    )
    return {
        "msgtype": "template_card",
        "template_card": {
            "card_type": "button_interaction",
            "source": {"desc": "12306 助手"},
            "main_title": {"title": "发现余票，是否预定？", "desc": task_name},
            "sub_title_text": summary,
            "button_list": [
                {
                    "text": "确认预定",
                    "style": 1,
                    "key": f"ticket_confirm:confirm:{confirmation_id}:{raw_token}",
                },
                {
                    "text": "忽略",
                    "style": 2,
                    "key": f"ticket_confirm:ignore:{confirmation_id}:{raw_token}",
                },
            ],
            "task_id": f"ticket_confirmation_{confirmation_id}",
        },
    }


def parse_confirmation_event(frame: dict) -> Optional[tuple[str, int, str, str]]:
    """Parse our button event from a WeCom SDK event frame."""
    body = frame.get("body", {}) if isinstance(frame, dict) else {}
    event = body.get("event", {}) if isinstance(body, dict) else {}
    event_key = event.get("event_key", "")
    if not isinstance(event_key, str) or not event_key.startswith("ticket_confirm:"):
        return None

    parts = event_key.split(":", 3)
    if len(parts) != 4 or parts[1] not in {"confirm", "ignore"}:
        return None
    try:
        confirmation_id = int(parts[2])
    except ValueError:
        return None

    actor_id = ""
    for source in (event.get("from"), body.get("from"), event):
        if isinstance(source, dict):
            actor_id = (
                source.get("userid")
                or source.get("user_id")
                or source.get("external_userid")
                or actor_id
            )
            if actor_id:
                break

    return parts[1], confirmation_id, parts[3], str(actor_id or "")


class WeComConfirmationBot:
    """Small lifecycle wrapper around the official WeCom WebSocket SDK."""

    def __init__(self, action_handler: Optional[ConfirmationActionHandler] = None):
        self._action_handler = action_handler
        self._client = None
        self._connect_task: Optional[asyncio.Task] = None

    @property
    def enabled(self) -> bool:
        return bool(
            settings.WECOM_BOT_ENABLED
            and settings.WECOM_BOT_ID
            and settings.WECOM_BOT_SECRET
            and settings.WECOM_BOT_CHAT_ID
        )

    def set_action_handler(self, handler: ConfirmationActionHandler) -> None:
        self._action_handler = handler

    async def start(self) -> None:
        if not self.enabled or self._client is not None:
            return
        from aibot import WSClient, WSClientOptions

        self._client = WSClient(
            WSClientOptions(
                bot_id=settings.WECOM_BOT_ID,
                secret=settings.WECOM_BOT_SECRET,
            )
        )

        @self._client.on("event.template_card_event")
        async def _on_card_event(frame):
            parsed = parse_confirmation_event(frame)
            if parsed is None or self._action_handler is None:
                return
            try:
                await self._action_handler(*parsed)
            except Exception:
                logger.exception("处理企业微信确认按钮事件失败")

        @self._client.on("error")
        def _on_error(error):
            logger.error("企业微信智能机器人错误: %s", error)

        self._connect_task = asyncio.create_task(self._client.connect())
        logger.info("企业微信智能机器人连接任务已启动")

    async def stop(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            try:
                client.disconnect()
            except Exception:
                logger.exception("关闭企业微信智能机器人连接失败")
        if self._connect_task:
            if not self._connect_task.done():
                self._connect_task.cancel()
            self._connect_task = None

    async def send_confirmation(self, card_body: dict) -> None:
        if not self.enabled:
            raise RuntimeError("企业微信智能机器人未配置")
        if self._client is None:
            raise RuntimeError("企业微信智能机器人尚未启动")
        await self._client.send_message(settings.WECOM_BOT_CHAT_ID, card_body)

    async def send_text(self, content: str) -> None:
        if not self.enabled or self._client is None:
            logger.warning("企业微信机器人未启用，消息未发送: %s", content)
            return
        await self._client.send_message(
            settings.WECOM_BOT_CHAT_ID,
            {"msgtype": "text", "text": {"content": content}},
        )


_bot: Optional[WeComConfirmationBot] = None


def get_wecom_confirmation_bot() -> WeComConfirmationBot:
    global _bot
    if _bot is None:
        _bot = WeComConfirmationBot()
    return _bot
