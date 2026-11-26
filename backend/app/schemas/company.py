from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class SubscriptionPlanCreate(BaseModel):
    name: str
    tier: str = "starter" # starter, growth, enterprise
    max_employees: int = 5
    max_leads: int = 10000
    recording_retention_days: int = 30
    has_auto_dialer: bool = False
    has_sentiment_analysis: bool = False

class SubscriptionPlanResponse(BaseModel):
    id: str
    name: str
    tier: str
    max_employees: int
    max_leads: int
    recording_retention_days: int
    has_auto_dialer: bool
    has_sentiment_analysis: bool
    is_active: bool

    class Config:
        from_attributes = True

class CompanyCreate(BaseModel):
    name: str
    subdomain: str
    plan_id: str
    admin_name: str
    admin_email: str
    admin_password: str
    admin_phone: str

class CompanyResponse(BaseModel):
    id: str
    name: str
    subdomain: str
    plan_id: str
    plan_name: Optional[str] = None
    is_active: bool
    user_count: Optional[int] = 0
    lead_count: Optional[int] = 0
    created_at: datetime

    class Config:
        from_attributes = True

class TelephonyConfigUpdate(BaseModel):
    provider: str # exotel, ozonetel, knowlarity, myoperator, twilio, mock
    api_key: str
    api_token: str
    account_sid: Optional[str] = None
    virtual_number: str
    webhook_secret: Optional[str] = None
    recording_consent_enabled: bool = True
    consent_announcement_text: Optional[str] = "This call is recorded for quality and training purposes."
    retention_days: int = 30
    is_active: bool = True
    allow_manual_dialing: Optional[bool] = True
    working_hours_start: Optional[str] = "09:00"
    working_hours_end: Optional[str] = "19:00"
    allow_agent_bulk_upload: Optional[bool] = False

class TelephonyConfigResponse(BaseModel):
    id: str
    provider: str
    virtual_number: str
    recording_consent_enabled: bool
    consent_announcement_text: Optional[str]
    retention_days: int
    is_active: bool
    allow_manual_dialing: bool = True
    working_hours_start: Optional[str] = "09:00"
    working_hours_end: Optional[str] = "19:00"
    allow_agent_bulk_upload: bool = False

    class Config:
        from_attributes = True
