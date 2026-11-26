from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime

class LeadStageCreate(BaseModel):
    name: str
    color_hex: str = "#3B82F6"
    order_index: int = 0
    is_terminal: bool = False

class LeadStageResponse(BaseModel):
    id: str
    name: str
    color_hex: str
    order_index: int
    is_terminal: bool

    class Config:
        from_attributes = True

class LeadCreate(BaseModel):
    first_name: str
    last_name: Optional[str] = ""
    phone: str
    alternate_phone: Optional[str] = None
    email: Optional[str] = None
    city: Optional[str] = None
    source: Optional[str] = "Manual"
    stage_id: Optional[str] = None
    assigned_to: Optional[str] = None
    tags: Optional[List[str]] = []
    custom_fields: Optional[Dict[str, Any]] = {}

class LeadUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    alternate_phone: Optional[str] = None
    email: Optional[str] = None
    city: Optional[str] = None
    stage_id: Optional[str] = None
    assigned_to: Optional[str] = None
    tags: Optional[List[str]] = None
    custom_fields: Optional[Dict[str, Any]] = None

class LeadResponse(BaseModel):
    id: str
    first_name: str
    last_name: Optional[str] = ""
    phone: str
    alternate_phone: Optional[str] = None
    email: Optional[str] = None
    city: Optional[str] = None
    source: str
    stage_id: str
    stage_name: Optional[str] = None
    stage_color: Optional[str] = None
    assigned_to: Optional[str] = None
    assigned_to_name: Optional[str] = None
    total_calls_count: int
    last_call_at: Optional[datetime] = None
    next_followup_at: Optional[datetime] = None
    tags: Optional[List[str]] = []
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class LeadAllocationHistoryItem(BaseModel):
    id: str
    assigned_by_name: str
    from_user_name: Optional[str] = None
    to_user_name: str
    transfer_reason: Optional[str] = None
    allocated_at: datetime

class LeadDetailResponse(LeadResponse):
    allocation_history: List[LeadAllocationHistoryItem] = []
    call_logs: List[Any] = []
    follow_ups: List[Any] = []

class LeadImportRowError(BaseModel):
    row_number: int
    phone: Optional[str] = None
    reason: str

class LeadImportResult(BaseModel):
    total_rows: int
    successful_imports: int
    duplicate_skipped: int
    failed_rows: int
    errors: List[LeadImportRowError] = []

class SingleAssignRequest(BaseModel):
    employee_id: str

class BulkAssignRequest(BaseModel):
    lead_ids: List[str]
    employee_ids: List[str]
    mode: str = "equal" # 'equal' or 'custom'
    custom_counts: Optional[Dict[str, int]] = None # {emp_id: count}

class TransferLeadsRequest(BaseModel):
    lead_ids: List[str]
    to_employee_id: str
    transfer_reason: str
