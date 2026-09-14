#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
核心配置模块

包含应用的所有配置项
"""

import os
import sys
from pathlib import Path
from functools import lru_cache

try:
    from pydantic import field_validator
    from pydantic_settings import BaseSettings
except ImportError:
    class BaseSettings:
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)

    def field_validator(*args, **kwargs):
        def decorator(func):
            return func
        return decorator


def get_data_dir() -> Path:
    android_data_dir = os.environ.get("ANDROID_DATA_DIR")
    if android_data_dir:
        return Path(android_data_dir)

    if getattr(sys, "frozen", False):
        base_path = Path(sys.executable).parent
    else:
        base_path = Path(__file__).parent.parent.parent

    return base_path / "data"


class Settings(BaseSettings):
    """应用配置"""

    APP_NAME: str = "12306 自动化抢票系统"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True

    API_V1_PREFIX: str = "/api/v1"

    @property
    def DATA_DIR(self) -> Path:
        return get_data_dir()

    @property
    def DATABASE_URL(self) -> str:
        db_path = self.DATA_DIR / "12306.db"
        return f"sqlite+aiosqlite:///{db_path}"

    @property
    def SESSION_DIR(self) -> str:
        return str(self.DATA_DIR / "sessions")

    SCHEDULER_TIMEZONE: str = "Asia/Shanghai"
    DEFAULT_QUERY_INTERVAL: int = 5
    MIN_QUERY_INTERVAL: int = 3
    MAX_QUERY_INTERVAL: int = 60

    # 企业微信智能机器人（官方 WebSocket SDK）
    WECOM_BOT_ENABLED: bool = False
    WECOM_BOT_ID: str = ""
    WECOM_BOT_SECRET: str = ""
    WECOM_BOT_CHAT_ID: str = ""
    WECOM_ALLOWED_USER_IDS: str = ""
    WECOM_CONFIRM_EXPIRE_SECONDS: int = 60

    @property
    def WECOM_ALLOWED_USERS(self) -> set[str]:
        return {
            item.strip()
            for item in (self.WECOM_ALLOWED_USER_IDS or "").split(",")
            if item.strip()
        }

    @property
    def STATION_FILE(self) -> str:
        return str(self.DATA_DIR / "assets" / "station_name.js")

    LOG_LEVEL: str = "INFO"
    TERMINAL_LOG_BUFFER_SIZE: int = 2000

    @property
    def LOG_DIR(self) -> str:
        return str(self.DATA_DIR / "logs")

    CORS_ORIGINS: list = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
        "null",
        "file://",
    ]

    SECRET_KEY: str = "please-change-secret-key-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7
    ENABLE_TERMINAL_LOG_STREAM: bool = False

    @field_validator("DEBUG", "WECOM_BOT_ENABLED", mode="before")
    @classmethod
    def parse_bool_env(cls, value):
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on", "debug", "development", "dev"}:
                return True
            if normalized in {"0", "false", "no", "off", "release", "production", "prod"}:
                return False
        return value

    @field_validator("WECOM_CONFIRM_EXPIRE_SECONDS", mode="before")
    @classmethod
    def clamp_wecom_expiry(cls, value):
        try:
            seconds = int(value)
        except (TypeError, ValueError):
            seconds = 60
        return max(15, min(300, seconds))

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()


def ensure_directories():
    settings = get_settings()
    dirs = [
        settings.DATA_DIR,
        Path(settings.SESSION_DIR),
        Path(settings.LOG_DIR),
        settings.DATA_DIR / "assets",
    ]
    for directory in dirs:
        directory.mkdir(parents=True, exist_ok=True)

    print(f"[配置] 数据目录: {settings.DATA_DIR}")
    print(f"[配置] 数据库路径: {settings.DATABASE_URL}")
