from sqlalchemy import Column, String, Boolean, Integer, Numeric, DateTime, ForeignKey, Text, UniqueConstraint, JSON
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from backend.app.database import Base, generate_uuid

def utcnow():
    return datetime.now(timezone.utc)

class CallDisposition(Base):
    __tablename__ = "call_dispositions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    company_id = Column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    code = Column(String(50), nullable=False) # INTERESTED, BUSY, WRONG_NUMBER, CALLBACK, NOT_REACHABLE, CONVERTED
    label = Column(String(100), nullable=False)
    requires_followup = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)

    __table_args__ = (
        UniqueConstraint("company_id", "code", name="uq_company_disposition"),
    )

    company = relationship("Company", back_populates="dispositions")
    call_logs = relationship("CallLog", back_populates="disposition")

    @property
    def name(self):
        return self.label

class CallLog(Base):
    __tablename__ = "call_logs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    company_id = Column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    lead_id = Column(String(36), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True)
    telecaller_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    direction = Column(String(20), default="outbound") # outbound, inbound
    provider_call_sid = Column(String(100), nullable=True, index=True)
    caller_number = Column(String(20), nullable=False)
    callee_number = Column(String(20), nullable=False)
    status = Column(String(30), default="initiated") # initiated, ringing, connected, busy, no_answer, failed, missed, completed
    started_at = Column(DateTime, default=utcnow, index=True)
    answered_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Integer, default=0)
    talk_time_seconds = Column(Integer, default=0)
    
    # Recording fields
    recording_url = Column(Text, nullable=True)
    recording_file_path = Column(Text, nullable=True)
    recording_duration_seconds = Column(Integer, default=0)
    recording_status = Column(String(30), default="pending") # pending, available, purged
    consent_announced = Column(Boolean, default=True)

    # Mandatory Disposition & Notes (next call blocked if disposition_id is null)
    disposition_id = Column(String(36), ForeignKey("call_dispositions.id"), nullable=True)
    disposition_submitted_at = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=utcnow)

    lead = relationship("Lead", back_populates="call_logs")
    telecaller = relationship("User", back_populates="call_logs", foreign_keys=[telecaller_id])
    disposition = relationship("CallDisposition", back_populates="call_logs")
    analytics = relationship("CallAnalytics", back_populates="call_log", uselist=False, cascade="all, delete-orphan")

class CallAnalytics(Base):
    __tablename__ = "call_analytics"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    company_id = Column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    call_log_id = Column(String(36), ForeignKey("call_logs.id", ondelete="CASCADE"), nullable=False, unique=True)
    transcript = Column(Text, nullable=True)
    sentiment = Column(String(20), nullable=True) # positive, neutral, negative
    overall_score = Column(Numeric(4, 2), nullable=True) # 0.00 to 100.00
    talk_ratio = Column(Numeric(4, 2), nullable=True) # agent vs customer
    silence_ratio = Column(Numeric(4, 2), nullable=True)
    detected_keywords = Column(JSON, default=list) # e.g. ["cancel", "expensive"]
    ai_summary = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    call_log = relationship("CallLog", back_populates="analytics")
