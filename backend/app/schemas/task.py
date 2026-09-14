#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""任务相关的 Pydantic 模式。"""

from datetime import datetime
from enum import Enum
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


class TaskStatusEnum(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PassengerInfo(BaseModel):
    passenger_name: str
    passenger_id_no: str
    passenger_id_type_code: str = "1"
    passenger_type: str = "1"
    mobile_no: str = ""


class TaskCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    from_station: str
    to_station: str
    train_date: Optional[str] = Field(None, description="固定日期策略下必填 YYYY-MM-DD")

    train_codes: Optional[List[str]] = None
    train_types: Optional[List[str]] = None
    seat_types: List[str]
    start_time_range: Optional[str] = None
    passengers: List[PassengerInfo] = Field(..., min_length=1)

    query_interval: int = Field(5, ge=3, le=60)
    max_retry_count: int = Field(100, description="最大重试次数（-1表示无限）")
    auto_submit: bool = True

    schedule_mode: Literal["once", "daily"] = "once"
    daily_start_time: Optional[str] = None
    date_strategy: Literal["fixed", "offset"] = "fixed"
    date_offset_days: int = Field(0, ge=0)
    confirmation_required: bool = False

    @model_validator(mode="after")
    def validate_schedule(self):
        if self.date_strategy == "fixed" and not self.train_date:
            raise ValueError("固定日期策略必须填写 train_date")
        if self.schedule_mode == "daily":
            if not self.daily_start_time:
                raise ValueError("每日任务必须填写 daily_start_time")
            if not self.confirmation_required:
                raise ValueError("每日任务当前必须启用企业微信人工确认")
        return self


class TaskUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    from_station: Optional[str] = None
    to_station: Optional[str] = None
    train_date: Optional[str] = None
    train_codes: Optional[List[str]] = None
    train_types: Optional[List[str]] = None
    seat_types: Optional[List[str]] = None
    start_time_range: Optional[str] = None
    passengers: Optional[List[PassengerInfo]] = None
    query_interval: Optional[int] = Field(None, ge=3, le=60)
    max_retry_count: Optional[int] = None
    auto_submit: Optional[bool] = None

    schedule_mode: Optional[Literal["once", "daily"]] = None
    daily_start_time: Optional[str] = None
    date_strategy: Optional[Literal["fixed", "offset"]] = None
    date_offset_days: Optional[int] = Field(None, ge=0)
    confirmation_required: Optional[bool] = None


class TaskResponse(BaseModel):
    id: int
    user_id: int
    name: str
    from_station: str
    to_station: str
    train_date: str
    train_codes: Optional[str]
    train_types: Optional[str]
    seat_types: str
    start_time_range: Optional[str]
    passengers: str
    query_interval: int
    max_retry_count: int
    auto_submit: bool

    schedule_mode: str = "once"
    daily_start_time: Optional[str] = None
    date_strategy: str = "fixed"
    date_offset_days: int = 0
    confirmation_required: bool = False
    last_daily_run_date: Optional[str] = None
    last_daily_success_date: Optional[str] = None

    status: TaskStatusEnum
    retry_count: int
    order_id: Optional[str]
    result_message: Optional[str]
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]

    class Config:
        from_attributes = True


class TaskListResponse(BaseModel):
    total: int
    tasks: List[TaskResponse]


class TaskLogResponse(BaseModel):
    id: int
    task_id: int
    level: str
    message: str
    details: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class TaskLogsResponse(BaseModel):
    total: int
    logs: List[TaskLogResponse]
