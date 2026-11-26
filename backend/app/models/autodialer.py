from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from backend.app.database import Base, generate_uuid

def utcnow():
    return datetime.now(timezone.utc)

class AutoDialerSession(Base):
    __tablename__ = "autodialer_sessions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    company_id = Column(String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False, default="Auto-Dialer Session")
    mode = Column(String(20), nullable=False, default="preview") # 'preview' or 'progressive'
    status = Column(String(20), nullable=False, default="running") # 'running', 'paused', 'completed', 'stopped'
    
    lead_ids = Column(JSON, default=list) # List of lead UUIDs in dial order
    current_index = Column(Integer, default=0)
    total_leads = Column(Integer, default=0)
    dialed_count = Column(Integer, default=0)
    connected_count = Column(Integer, default=0)
    skipped_count = Column(Integer, default=0)

    countdown_seconds = Column(Integer, default=10) # For preview mode
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    user = relationship("User")
