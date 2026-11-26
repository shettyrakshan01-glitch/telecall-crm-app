from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class CallDispositionCreate(BaseModel):
    code: Optional[str] = None
    label: str
    requires_followup: bool = False

class CallDispositionUpdate(BaseModel):
    label: Optional[str] = None
    requires_followup: Optional[bool] = None
    is_active: Optional[bool] = None

class CallDispositionResponse(BaseModel):
    id: str
    code: str
    label: str
    name: Optional[str] = None
    requires_followup: bool
    is_active: bool

    class Config:
        from_attributes = True

class InitiateCallRequest(BaseModel):
    lead_id: Optional[str] = None
    phone: Optional[str] = None
    dial_method: Optional[str] = "cloud" # "sim" or "cloud"

class EndCallRequest(BaseModel):
    call_log_id: Optional[str] = None
    call_id: Optional[str] = None
    duration_seconds: int = 0
    talk_time_seconds: int = 0
    status: str = "completed" # completed, busy, no_answer, failed
    recording_url: Optional[str] = None
    call_notes: Optional[str] = None

class SubmitDispositionRequest(BaseModel):
    call_log_id: Optional[str] = None
    call_id: Optional[str] = None
    disposition_id: str
    notes: Optional[str] = ""
    # Optional immediate follow-up creation in the same action
    next_followup_at: Optional[datetime] = None
    followup_notes: Optional[str] = None
    followup_priority: Optional[str] = "normal"
    update_lead_stage_id: Optional[str] = None
    customer_name: Optional[str] = None

class CallLogResponse(BaseModel):
    id: str
    lead_id: str
    lead_name: Optional[str] = None
    lead_phone: Optional[str] = None
    telecaller_id: str
    telecaller_name: Optional[str] = None
    direction: str
    provider_call_sid: Optional[str] = None
    caller_number: str
    callee_number: str
    status: str
    started_at: datetime
    answered_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    duration_seconds: int
    talk_time_seconds: int
    recording_url: Optional[str] = None
    disposition_id: Optional[str] = None
    disposition_label: Optional[str] = None
    notes: Optional[str] = None
    disposition_submitted_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class AgentCallGateStatus(BaseModel):
    is_blocked: bool
    blocking_call_id: Optional[str] = None
    blocking_lead_id: Optional[str] = None
    blocking_lead_name: Optional[str] = None
    message: Optional[str] = None
