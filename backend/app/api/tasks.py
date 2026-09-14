#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""任务相关 API 接口。"""

import json
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import get_current_user
from ..core.database import get_db
from ..models.task import Task, TaskLog, TaskStatus
from ..models.user import User
from ..schemas.common import ResponseBase
from ..schemas.task import (
    TaskCreate,
    TaskListResponse,
    TaskLogResponse,
    TaskLogsResponse,
    TaskResponse,
    TaskStatusEnum,
    TaskUpdate,
)
from ..services.confirmation_domain import china_now, parse_daily_start_time
from ..tasks.confirmation_runner import get_confirmation_runner
from ..tasks.scheduler import get_scheduler

router = APIRouter(prefix="/tasks", tags=["任务"])


async def _get_owned_task(task_id: int, current_user_id: int, db: AsyncSession) -> Task:
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.user_id != current_user_id:
        raise HTTPException(status_code=403, detail="无权访问该任务")
    return task


def _validate_daily_fields(task: Task) -> None:
    if task.schedule_mode != "daily":
        return
    if not task.daily_start_time:
        raise HTTPException(status_code=400, detail="每日任务必须配置启动时间")
    try:
        parse_daily_start_time(task.daily_start_time)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not task.confirmation_required:
        raise HTTPException(status_code=400, detail="每日任务必须启用企业微信人工确认")
    if task.date_strategy == "fixed" and not task.train_date:
        raise HTTPException(status_code=400, detail="固定日期策略必须配置乘车日期")


@router.post("", response_model=ResponseBase[TaskResponse])
async def create_task(
    task_data: TaskCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not current_user.is_logged_in:
        raise HTTPException(status_code=400, detail="用户未登录，请先登录 12306")

    train_date = task_data.train_date or china_now().date().isoformat()
    task = Task(
        user_id=current_user.id,
        name=task_data.name,
        from_station=task_data.from_station,
        to_station=task_data.to_station,
        train_date=train_date,
        train_codes=",".join(task_data.train_codes) if task_data.train_codes else None,
        train_types=",".join(task_data.train_types) if task_data.train_types else None,
        seat_types=",".join(task_data.seat_types),
        start_time_range=task_data.start_time_range,
        passengers=json.dumps([p.model_dump() for p in task_data.passengers], ensure_ascii=False),
        query_interval=task_data.query_interval,
        max_retry_count=task_data.max_retry_count,
        # Daily jobs are always human-confirmed and never enter the legacy direct-submit path.
        auto_submit=False if task_data.schedule_mode == "daily" else task_data.auto_submit,
        schedule_mode=task_data.schedule_mode,
        daily_start_time=task_data.daily_start_time,
        date_strategy=task_data.date_strategy,
        date_offset_days=task_data.date_offset_days,
        confirmation_required=task_data.confirmation_required,
        status=TaskStatus.PENDING,
    )
    _validate_daily_fields(task)

    db.add(task)
    await db.commit()
    await db.refresh(task)
    db.add(TaskLog(
        task_id=task.id,
        level="info",
        message=(
            f"任务创建成功: {task.from_station} -> {task.to_station} ({task.train_date})"
            + (f"，每日 {task.daily_start_time} 企业微信确认" if task.schedule_mode == "daily" else "")
        ),
    ))
    await db.commit()

    if task.schedule_mode == "daily":
        await get_confirmation_runner().register_task(task.id)

    return ResponseBase(success=True, message="任务创建成功", data=TaskResponse.model_validate(task))


@router.get("", response_model=TaskListResponse)
async def list_tasks(
    status: Optional[TaskStatusEnum] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Task).where(Task.user_id == current_user.id)
    if status:
        stmt = stmt.where(Task.status == TaskStatus(status.value))
    stmt = stmt.order_by(Task.created_at.desc()).offset(skip).limit(limit)
    tasks = (await db.execute(stmt)).scalars().all()

    count_stmt = select(func.count()).select_from(Task).where(Task.user_id == current_user.id)
    if status:
        count_stmt = count_stmt.where(Task.status == TaskStatus(status.value))
    total = (await db.execute(count_stmt)).scalar_one()
    return TaskListResponse(total=total, tasks=[TaskResponse.model_validate(t) for t in tasks])


@router.get("/{task_id}", response_model=ResponseBase[TaskResponse])
async def get_task(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    task = await _get_owned_task(task_id, current_user.id, db)
    return ResponseBase(success=True, data=TaskResponse.model_validate(task))


@router.put("/{task_id}", response_model=ResponseBase[TaskResponse])
async def update_task(
    task_id: int,
    task_data: TaskUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    task = await _get_owned_task(task_id, current_user.id, db)
    if task.status == TaskStatus.RUNNING:
        raise HTTPException(status_code=400, detail="运行中的任务无法修改")

    old_schedule_mode = task.schedule_mode
    update_data = task_data.model_dump(exclude_unset=True)
    if "passengers" in update_data:
        update_data["passengers"] = json.dumps(update_data["passengers"], ensure_ascii=False)
    for list_field in ("train_codes", "train_types", "seat_types"):
        if list_field in update_data:
            value = update_data[list_field]
            update_data[list_field] = ",".join(value) if value else None

    for key, value in update_data.items():
        setattr(task, key, value)
    if task.schedule_mode == "daily":
        task.auto_submit = False
    _validate_daily_fields(task)

    task.updated_at = china_now()
    await db.commit()
    await db.refresh(task)

    runner = get_confirmation_runner()
    if old_schedule_mode == "daily" and task.schedule_mode != "daily":
        await runner.pause_task(task.id)
    if task.schedule_mode == "daily" and task.status not in {TaskStatus.PAUSED, TaskStatus.CANCELLED}:
        await runner.register_task(task.id)

    return ResponseBase(success=True, message="任务更新成功", data=TaskResponse.model_validate(task))


@router.delete("/{task_id}", response_model=ResponseBase)
async def delete_task(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    task = await _get_owned_task(task_id, current_user.id, db)
    if task.status == TaskStatus.RUNNING:
        raise HTTPException(status_code=400, detail="运行中的任务无法删除，请先停止")
    if task.schedule_mode == "daily":
        await get_confirmation_runner().pause_task(task.id)
    await db.delete(task)
    await db.commit()
    return ResponseBase(success=True, message="任务删除成功")


@router.post("/{task_id}/start", response_model=ResponseBase)
async def start_task(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    task = await _get_owned_task(task_id, current_user.id, db)

    if task.schedule_mode == "daily":
        _validate_daily_fields(task)
        task.status = TaskStatus.PENDING
        task.retry_count = 0
        db.add(TaskLog(task_id=task.id, level="info", message="每日企业微信确认计划已启用"))
        await db.commit()
        await get_confirmation_runner().register_task(task.id)
        return ResponseBase(success=True, message="每日计划已启用")

    if task.status == TaskStatus.RUNNING:
        raise HTTPException(status_code=400, detail="任务已在运行中")
    if task.status == TaskStatus.SUCCESS:
        raise HTTPException(status_code=400, detail="任务已成功完成")

    task.status = TaskStatus.RUNNING
    task.started_at = china_now()
    task.retry_count = 0
    db.add(TaskLog(task_id=task.id, level="info", message="任务已启动"))
    await db.commit()
    await get_scheduler().start_task(task_id)
    return ResponseBase(success=True, message="任务已启动")


@router.post("/{task_id}/stop", response_model=ResponseBase)
async def stop_task(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    task = await _get_owned_task(task_id, current_user.id, db)

    if task.schedule_mode == "daily":
        if task.status == TaskStatus.PAUSED:
            raise HTTPException(status_code=400, detail="每日计划已暂停")
        task.status = TaskStatus.PAUSED
        db.add(TaskLog(task_id=task.id, level="info", message="每日企业微信确认计划已暂停"))
        await db.commit()
        await get_confirmation_runner().pause_task(task.id)
        return ResponseBase(success=True, message="每日计划已暂停")

    if task.status != TaskStatus.RUNNING:
        raise HTTPException(status_code=400, detail="任务未在运行中")
    task.status = TaskStatus.PAUSED
    db.add(TaskLog(task_id=task.id, level="info", message="任务已暂停"))
    await db.commit()
    await get_scheduler().stop_task(task_id)
    return ResponseBase(success=True, message="任务已暂停")


@router.post("/{task_id}/cancel", response_model=ResponseBase)
async def cancel_task(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    task = await _get_owned_task(task_id, current_user.id, db)
    if task.schedule_mode != "daily" and task.status == TaskStatus.SUCCESS:
        raise HTTPException(status_code=400, detail="已成功的任务无法取消")

    task.status = TaskStatus.CANCELLED
    task.finished_at = china_now()
    db.add(TaskLog(task_id=task.id, level="warning", message="任务已取消"))
    await db.commit()

    if task.schedule_mode == "daily":
        await get_confirmation_runner().pause_task(task.id)
    else:
        await get_scheduler().stop_task(task_id)
    return ResponseBase(success=True, message="任务已取消")


@router.get("/{task_id}/logs", response_model=TaskLogsResponse)
async def get_task_logs(
    task_id: int,
    level: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    task = await _get_owned_task(task_id, current_user.id, db)
    stmt = select(TaskLog).where(TaskLog.task_id == task.id)
    if level:
        stmt = stmt.where(TaskLog.level == level)
    stmt = stmt.order_by(TaskLog.created_at.desc()).offset(skip).limit(limit)
    logs = (await db.execute(stmt)).scalars().all()
    return TaskLogsResponse(total=len(logs), logs=[TaskLogResponse.model_validate(log) for log in logs])
