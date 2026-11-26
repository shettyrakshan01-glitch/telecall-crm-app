from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from backend.app.database import Base, generate_uuid

def utcnow():
    return datetime.now(timezone.utc)

class FollowUp(Base):
    __tablename__ = "follow_ups"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    company_id = Column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    lead_id = Column(String(36), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True)
    call_log_id = Column(String(36), ForeignKey("call_logs.id"), nullable=True)
    assigned_to = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    scheduled_at = Column(DateTime, nullable=False, index=True)
    status = Column(String(20), default="pending", index=True) # pending, completed, cancelled, rescheduled
    priority = Column(String(20), default="normal") # low, normal, high
    is_missed_call_callback = Column(Boolean, default=False)
    notes = Column(Text, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    lead = relationship("Lead", back_populates="follow_ups")
    assignee = relationship("User", foreign_keys=[assigned_to], back_populates="follow_ups")
    creator = relationship("User", foreign_keys=[created_by])
    call_log = relationship("CallLog")
