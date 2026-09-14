#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Read-only confirmation status API for task owners."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import get_current_user
from ..core.database import get_db
from ..models.confirmation import TicketConfirmation
from ..models.task import Task
from ..models.user import User
from ..schemas.confirmation import ConfirmationListResponse, ConfirmationResponse

router = APIRouter(prefix="/confirmations", tags=["企业微信确认"])


@router.get("/task/{task_id}", response_model=ConfirmationListResponse)
async def list_task_confirmations(
    task_id: int,
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问该任务")

    result = await db.execute(
        select(TicketConfirmation)
        .where(TicketConfirmation.task_id == task_id)
        .order_by(TicketConfirmation.created_at.desc())
        .limit(limit)
    )
    confirmations = result.scalars().all()
    return ConfirmationListResponse(
        total=len(confirmations),
        confirmations=[ConfirmationResponse.model_validate(item) for item in confirmations],
    )
