from sqlalchemy import Column, Integer, String, Text, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB
from database import Base


class Event(Base):
    __tablename__ = "events"

    id         = Column(Integer, primary_key=True, index=True)
    user_id    = Column(Integer, nullable=False)
    event_type = Column(String, nullable=False)
    payload    = Column(JSONB, default={})
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class EventAudit(Base):
    __tablename__ = "events_audit"

    id         = Column(Integer, primary_key=True, index=True)
    operation  = Column(String, nullable=False)
    changed_at = Column(DateTime(timezone=True), server_default=func.now())
    changed_by = Column(Text)
    old_data   = Column(JSONB)
    new_data   = Column(JSONB)
