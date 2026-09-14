#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""12306 自动化抢票系统 - FastAPI 后端入口。"""

import asyncio
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.api import auth, confirmations, config, logs, tasks, trains, users
from app.core.config import ensure_directories, get_settings
from app.core.database import close_db, init_db
from app.core.terminal_logs import (
    bind_terminal_log_loop,
    install_terminal_capture,
    uninstall_terminal_capture,
)
from app.services.ticket_confirmation_service import get_ticket_confirmation_service
from app.services.wecom_confirmation import get_wecom_confirmation_bot
from app.tasks.confirmation_runner import get_confirmation_runner
from app.tasks.scheduler import get_scheduler

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    bind_terminal_log_loop(asyncio.get_running_loop())
    install_terminal_capture()

    print("\n" + "=" * 50)
    print(f"{settings.APP_NAME} v{settings.APP_VERSION}")
    print("=" * 50)

    ensure_directories()
    await init_db()

    scheduler = get_scheduler()
    scheduler.start()
    await scheduler.resume_tasks()

    wecom_bot = get_wecom_confirmation_bot()
    confirmation_service = get_ticket_confirmation_service()
    confirmation_service.bot = wecom_bot
    wecom_bot.set_action_handler(confirmation_service.handle_action)
    await wecom_bot.start()

    confirmation_runner = get_confirmation_runner()
    confirmation_runner.start()

    print("[启动] 服务启动成功!")
    print("[启动] API 文档: http://localhost:8000/docs")
    if wecom_bot.enabled:
        print("[启动] 企业微信智能机器人确认已启用")
    else:
        print("[启动] 企业微信智能机器人未配置；每日确认任务不会执行")
    print("=" * 50 + "\n")

    try:
        yield
    finally:
        print("\n[关闭] 正在关闭服务...")
        confirmation_runner.shutdown()
        await wecom_bot.stop()
        scheduler.shutdown()
        await close_db()
        uninstall_terminal_capture()
        print("[关闭] 服务已关闭\n")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="""
    12306 自动化抢票系统 API

    * 认证模块：扫码/密码登录与会话管理
    * 查票模块：车票查询与车站搜索
    * 任务模块：一次性抢票与每日监控任务
    * 企业微信确认：发现余票后由用户点击确认，再重新查票并提交订单

    支付仍需在官方 12306 完成。
    """,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "message": str(exc),
            "error_code": "INTERNAL_ERROR",
        },
    )


app.include_router(auth.router, prefix=settings.API_V1_PREFIX)
app.include_router(users.router, prefix=settings.API_V1_PREFIX)
app.include_router(trains.router, prefix=settings.API_V1_PREFIX)
app.include_router(tasks.router, prefix=settings.API_V1_PREFIX)
app.include_router(confirmations.router, prefix=settings.API_V1_PREFIX)
app.include_router(logs.router, prefix=settings.API_V1_PREFIX)
app.include_router(config.router, prefix=settings.API_V1_PREFIX)


@app.get("/")
async def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "status": "running",
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
