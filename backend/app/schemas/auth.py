from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime

class Token(BaseModel):
    access_token: str
    token_type: str
    user_id: str
    email: str
    full_name: str
    role: str
    company_id: Optional[str] = None
    company_name: Optional[str] = None
    is_super_admin_session: Optional[bool] = False

class TokenPayload(BaseModel):
    sub: str # user_id
    email: str
    role: str
    company_id: Optional[str] = None

class LoginRequest(BaseModel):
    email: str
    password: str
    subdomain: Optional[str] = None # Optional for super_admin, required/matched for company users

class PasswordResetRequest(BaseModel):
    new_password: str

class UserProfileResponse(BaseModel):
    id: str
    email: str
    full_name: str
    phone: str
    role: str
    agent_status: str
    company_id: Optional[str] = None
    company_name: Optional[str] = None
    is_super_admin_session: Optional[bool] = False
    is_active: bool
    is_super_admin_session: Optional[bool] = False
    super_admin_email: Optional[str] = None

    class Config:
        from_attributes = True

class LoginHistoryResponse(BaseModel):
    id: str
    user_id: str
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    location_city: Optional[str] = None
    login_at: datetime
    logout_at: Optional[datetime] = None
    session_duration_seconds: Optional[int] = None

    class Config:
        from_attributes = True
