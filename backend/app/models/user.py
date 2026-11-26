from sqlalchemy import Column, String, Boolean, Integer, DateTime, ForeignKey, Text, UniqueConstraint, Date
from sqlalchemy.orm import relationship
from datetime import datetime, timezone, date
from backend.app.database import Base, generate_uuid

def utcnow():
    return datetime.now(timezone.utc)

class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    company_id = Column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=True) # Null for super_admin
    email = Column(String(100), nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(100), nullable=False)
    phone = Column(String(20), nullable=False)
    role = Column(String(20), nullable=False, default="telecaller") # super_admin, admin, manager, telecaller
    agent_status = Column(String(20), nullable=False, default="offline") # offline, idle, on_call, break, wrap_up
    status_updated_at = Column(DateTime, default=utcnow)
    telephony_agent_id = Column(String(50), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    session_timeout_minutes = Column(Integer, nullable=False, default=120)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        UniqueConstraint("company_id", "email", name="uq_company_user_email"),
    )

    company = relationship("Company", back_populates="users")
    assigned_leads = relationship("Lead", back_populates="assignee", foreign_keys="Lead.assigned_to")
    login_history = relationship("LoginHistory", back_populates="user", cascade="all, delete-orphan")
    shifts = relationship("TelecallerShift", back_populates="user", cascade="all, delete-orphan")
    call_logs = relationship("CallLog", back_populates="telecaller", foreign_keys="CallLog.telecaller_id")
    follow_ups = relationship("FollowUp", back_populates="assignee", foreign_keys="FollowUp.assigned_to")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")

class LoginHistory(Base):
    __tablename__ = "login_history"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    company_id = Column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(255), nullable=True)
    location_city = Column(String(100), nullable=True)
    login_at = Column(DateTime, default=utcnow)
    logout_at = Column(DateTime, nullable=True)
    session_duration_seconds = Column(Integer, nullable=True)

    user = relationship("User", back_populates="login_history")

class TelecallerShift(Base):
    __tablename__ = "telecaller_shifts"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    company_id = Column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    shift_date = Column(Date, default=date.today)
    clock_in_at = Column(DateTime, default=utcnow)
    clock_out_at = Column(DateTime, nullable=True)
    total_talk_time_sec = Column(Integer, default=0)
    total_idle_time_sec = Column(Integer, default=0)
    total_break_time_sec = Column(Integer, default=0)
    total_calls_handled = Column(Integer, default=0)

    user = relationship("User", back_populates="shifts")
    break_logs = relationship("BreakLog", back_populates="shift", cascade="all, delete-orphan")

class BreakLog(Base):
    __tablename__ = "break_logs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    shift_id = Column(String(36), ForeignKey("telecaller_shifts.id", ondelete="CASCADE"), nullable=False)
    break_reason = Column(String(100), nullable=False)
    started_at = Column(DateTime, default=utcnow)
    ended_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Integer, nullable=True)

    shift = relationship("TelecallerShift", back_populates="break_logs")
