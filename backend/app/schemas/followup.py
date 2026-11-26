from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class FollowUpCreate(BaseModel):
    lead_id: Optional[str] = None
    call_log_id: Optional[str] = None
    scheduled_at: datetime
    priority: str = "normal" # low, normal, high
    notes: Optional[str] = None
    assigned_to: Optional[str] = None # Defaults to current user if omitted

class FollowUpUpdate(BaseModel):
    scheduled_at: Optional[datetime] = None
    status: Optional[str] = None # pending, completed, cancelled, rescheduled
    priority: Optional[str] = None
    notes: Optional[str] = None

class FollowUpResponse(BaseModel):
    id: str
    lead_id: str
    lead_name: Optional[str] = None
    lead_phone: Optional[str] = None
    lead_city: Optional[str] = None
    assigned_to: str
    assigned_to_name: Optional[str] = None
    scheduled_at: datetime
    status: str
    priority: str
    is_missed_call_callback: bool
    notes: Optional[str] = None
    completed_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True

class FollowUpSummary(BaseModel):
    today_count: int
    tomorrow_count: int
    overdue_count: int
    completed_today_count: int
