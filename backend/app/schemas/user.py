from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime

class EmployeeCreate(BaseModel):
    full_name: str
    email: str
    phone: str
    password: str
    role: str = "telecaller" # admin, manager, telecaller
    telephony_agent_id: Optional[str] = None

class EmployeeUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[str] = None
    telephony_agent_id: Optional[str] = None
    is_active: Optional[bool] = None

class EmployeeResponse(BaseModel):
    id: str
    full_name: str
    email: str
    phone: str
    role: str
    agent_status: str
    status_updated_at: Optional[datetime] = None
    telephony_agent_id: Optional[str] = None
    is_active: bool
    assigned_leads_count: Optional[int] = 0
    today_calls_count: Optional[int] = 0
    today_talk_time_sec: Optional[int] = 0
    created_at: datetime

    class Config:
        from_attributes = True

class StatusUpdateRequest(BaseModel):
    status: str # offline, idle, on_call, break, wrap_up
    break_reason: Optional[str] = None # lunch, tea, meeting, etc.
