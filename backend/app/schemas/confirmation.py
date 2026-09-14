#!/usr/bin/env python
# -*- coding: utf-8 -*-

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class ConfirmationResponse(BaseModel):
    id: int
    task_id: int
    status: str
    train_date: str
    train_code: str
    seat_type: str
    seat_name: str
    seat_count_snapshot: Optional[str]
    expires_at: datetime
    confirmed_at: Optional[datetime]
    actor_id: Optional[str]
    order_id: Optional[str]
    details: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class ConfirmationListResponse(BaseModel):
    total: int
    confirmations: List[ConfirmationResponse]
