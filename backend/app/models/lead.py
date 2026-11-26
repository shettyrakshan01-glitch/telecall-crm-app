from sqlalchemy import Column, String, Boolean, Integer, DateTime, ForeignKey, Text, UniqueConstraint, JSON
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from backend.app.database import Base, generate_uuid

def utcnow():
    return datetime.now(timezone.utc)

class LeadStage(Base):
    __tablename__ = "lead_stages"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    company_id = Column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(50), nullable=False) # New, Interested, Not Interested, Callback, Converted, etc.
    color_hex = Column(String(10), default="#3B82F6")
    order_index = Column(Integer, default=0)
    is_terminal = Column(Boolean, default=False)
    is_system = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utcnow)

    __table_args__ = (
        UniqueConstraint("company_id", "name", name="uq_company_stage_name"),
    )

    company = relationship("Company", back_populates="stages")
    leads = relationship("Lead", back_populates="stage")

class LeadImportHistory(Base):
    __tablename__ = "lead_import_history"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    company_id = Column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    uploaded_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    file_name = Column(String(255), nullable=False)
    batch_name = Column(String(100), nullable=True)
    total_rows = Column(Integer, default=0)
    imported_count = Column(Integer, default=0)
    duplicates_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    status = Column(String(30), default="completed") # completed, processing, failed, undone
    error_report = Column(JSON, default=list) # [{row_number, phone, reason}]
    imported_lead_ids = Column(JSON, default=list) # List of lead IDs for Undo import
    created_at = Column(DateTime, default=utcnow, index=True)

    uploader = relationship("User", foreign_keys=[uploaded_by])
    leads = relationship("Lead", back_populates="import_batch")

class Lead(Base):
    __tablename__ = "leads"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    company_id = Column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=True)
    phone = Column(String(20), nullable=False, index=True)
    alternate_phone = Column(String(20), nullable=True)
    email = Column(String(100), nullable=True)
    city = Column(String(100), nullable=True)
    source = Column(String(50), default="Manual") # Manual, CSV Import, Website, etc.
    stage_id = Column(String(36), ForeignKey("lead_stages.id"), nullable=False, index=True)
    assigned_to = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    assigned_at = Column(DateTime, nullable=True)
    total_calls_count = Column(Integer, default=0)
    last_call_at = Column(DateTime, nullable=True)
    next_followup_at = Column(DateTime, nullable=True, index=True)
    tags = Column(JSON, default=list) # List of tag strings e.g. ["High Intent", "Budget Verified"]
    custom_fields = Column(JSON, default=dict)
    import_batch_id = Column(String(36), ForeignKey("lead_import_history.id", ondelete="SET NULL"), nullable=True, index=True)
    is_deleted = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utcnow, index=True)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        UniqueConstraint("company_id", "phone", name="uq_company_lead_phone"),
    )

    company = relationship("Company", back_populates="leads")
    stage = relationship("LeadStage", back_populates="leads")
    assignee = relationship("User", back_populates="assigned_leads", foreign_keys=[assigned_to])
    import_batch = relationship("LeadImportHistory", back_populates="leads", foreign_keys=[import_batch_id])
    call_logs = relationship("CallLog", back_populates="lead", cascade="all, delete-orphan", order_by="desc(CallLog.started_at)")
    follow_ups = relationship("FollowUp", back_populates="lead", cascade="all, delete-orphan", order_by="desc(FollowUp.scheduled_at)")
    allocation_history = relationship("LeadAllocation", back_populates="lead", cascade="all, delete-orphan", order_by="desc(LeadAllocation.allocated_at)")

class LeadAllocation(Base):
    __tablename__ = "lead_allocations"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    company_id = Column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    lead_id = Column(String(36), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True)
    assigned_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    from_user_id = Column(String(36), ForeignKey("users.id"), nullable=True) # Null if first-time assignment
    to_user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    transfer_reason = Column(Text, nullable=True)
    allocated_at = Column(DateTime, default=utcnow, index=True)

    lead = relationship("Lead", back_populates="allocation_history")
    assigner = relationship("User", foreign_keys=[assigned_by])
    from_user = relationship("User", foreign_keys=[from_user_id])
    to_user = relationship("User", foreign_keys=[to_user_id])
