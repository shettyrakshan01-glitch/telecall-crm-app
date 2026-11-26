from sqlalchemy import Column, String, Boolean, Integer, Numeric, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from backend.app.database import Base, generate_uuid

def utcnow():
    return datetime.now(timezone.utc)

class SubscriptionPlan(Base):
    __tablename__ = "subscription_plans"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(50), nullable=False, unique=True)
    tier = Column(String(20), nullable=False, default="starter") # starter, growth, enterprise
    max_employees = Column(Integer, nullable=False, default=5)
    max_leads = Column(Integer, nullable=False, default=10000)
    recording_retention_days = Column(Integer, nullable=False, default=30)
    has_auto_dialer = Column(Boolean, nullable=False, default=False)
    has_sentiment_analysis = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    companies = relationship("Company", back_populates="plan")

class Company(Base):
    __tablename__ = "companies"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    plan_id = Column(String(36), ForeignKey("subscription_plans.id"), nullable=False)
    name = Column(String(100), nullable=False)
    subdomain = Column(String(50), nullable=False, unique=True, index=True)
    is_active = Column(Boolean, nullable=False, default=True)
    storage_quota_gb = Column(Numeric(6, 2), default=10.00)
    used_storage_mb = Column(Numeric(10, 2), default=0.00)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    plan = relationship("SubscriptionPlan", back_populates="companies")
    users = relationship("User", back_populates="company", cascade="all, delete-orphan")
    leads = relationship("Lead", back_populates="company", cascade="all, delete-orphan")
    stages = relationship("LeadStage", back_populates="company", cascade="all, delete-orphan")
    dispositions = relationship("CallDisposition", back_populates="company", cascade="all, delete-orphan")
    telephony_config = relationship("TelephonyConfig", back_populates="company", uselist=False, cascade="all, delete-orphan")

class TelephonyConfig(Base):
    __tablename__ = "telephony_configs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    company_id = Column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, unique=True)
    provider = Column(String(30), nullable=False, default="mock") # exotel, ozonetel, knowlarity, myoperator, twilio, mock
    api_key = Column(String(255), nullable=False, default="")
    api_token = Column(String(255), nullable=False, default="")
    account_sid = Column(String(255), nullable=True)
    virtual_number = Column(String(30), nullable=False, default="")
    webhook_secret = Column(String(255), nullable=True)
    recording_consent_enabled = Column(Boolean, nullable=False, default=True)
    consent_announcement_text = Column(Text, default="This call is recorded for quality and training purposes.")
    retention_days = Column(Integer, nullable=False, default=30)
    is_active = Column(Boolean, nullable=False, default=True)
    
    # Dialer & Bulk Upload settings
    allow_manual_dialing = Column(Boolean, nullable=False, default=True)
    working_hours_start = Column(String(10), default="09:00")
    working_hours_end = Column(String(10), default="19:00")
    allow_agent_bulk_upload = Column(Boolean, nullable=False, default=False)
    
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    company = relationship("Company", back_populates="telephony_config")

class SuperAdminAudit(Base):
    __tablename__ = "superadmin_audits"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    super_admin_id = Column(String(36), nullable=False)
    super_admin_email = Column(String(100), nullable=False)
    target_company_id = Column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    target_user_id = Column(String(36), nullable=True)
    target_user_name = Column(String(100), nullable=True)
    target_role = Column(String(20), nullable=False) # admin or telecaller
    action_type = Column(String(50), nullable=False) # "impersonate_admin", "impersonate_agent", "audit_review"
    description = Column(String(255), nullable=False)
    ip_address = Column(String(45), nullable=True)
    created_at = Column(DateTime, default=utcnow)

