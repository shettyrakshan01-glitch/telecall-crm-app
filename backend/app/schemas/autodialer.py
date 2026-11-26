from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime

class StartDialerRequest(BaseModel):
    name: Optional[str] = "Auto-Dialer Campaign"
    mode: str = "preview" # 'preview' or 'progressive'
    countdown_seconds: int = 10
    filter_stage_id: Optional[str] = None
    custom_lead_ids: Optional[List[str]] = None

class AutoDialerSessionResponse(BaseModel):
    id: str
    user_id: str
    name: str
    mode: str
    status: str
    current_index: int
    total_leads: int
    dialed_count: int
    connected_count: int
    skipped_count: int
    countdown_seconds: int
    created_at: datetime

    class Config:
        from_attributes = True

class DialerNextLeadResponse(BaseModel):
    session_id: str
    status: str
    current_index: int
    total_leads: int
    progress_percentage: float
    mode: str
    countdown_seconds: int
    lead: Optional[Dict[str, Any]] = None
    is_finished: bool = False
