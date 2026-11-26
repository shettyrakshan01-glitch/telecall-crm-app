from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from backend.app.database import Base, generate_uuid

def utcnow():
    return datetime.now(timezone.utc)

class Notification(Base):
    __tablename__ = "notifications"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    company_id = Column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    type = Column(String(50), nullable=False) # lead_assigned, followup_due, missed_call, admin_alert
    title = Column(String(150), nullable=False)
    message = Column(Text, nullable=False)
    reference_id = Column(String(36), nullable=True) # lead_id or call_log_id
    is_read = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime, default=utcnow, index=True)

    user = relationship("User", back_populates="notifications")
