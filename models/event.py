from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Float, Boolean, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
from database import Base


class Event(Base):
    __tablename__ = "events"

    id            = Column(Integer, primary_key=True, index=True)
    user_id       = Column(Integer, nullable=False)
    owner_id      = Column(Integer, ForeignKey("users.id"), nullable=True)
    event_type    = Column(String, nullable=False)
    payload       = Column(JSONB, default={})
    embedding     = Column(Vector(3072), nullable=True)
    anomaly_score = Column(Float, nullable=True)
    is_anomaly    = Column(Boolean, default=False)
    created_at    = Column(DateTime(timezone=True), server_default=func.now())
    updated_at    = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    owner = relationship("User", back_populates="events")