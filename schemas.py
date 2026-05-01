from pydantic import BaseModel, Field
from typing import Any, Optional
from datetime import datetime


# ── Event schemas ──────────────────────────────────────────
class EventCreate(BaseModel):
    user_id:    int
    event_type: str
    payload:    dict[str, Any] = Field(default_factory=dict)

    model_config = {
        "json_schema_extra": {
            "example": {
                "user_id": 1,
                "event_type": "login",
                "payload": {
                    "ip": "192.168.1.1",
                    "country": "IN",
                    "device": "mobile",
                    "status": "success"
                }
            }
        }
    }


class EventUpdate(BaseModel):
    event_type: Optional[str]          = None
    payload:    Optional[dict[str, Any]] = None


class EventResponse(BaseModel):
    id:         int
    user_id:    int
    event_type: str
    payload:    dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Audit schemas ──────────────────────────────────────────
class AuditResponse(BaseModel):
    id:         int
    operation:  str
    changed_at: datetime
    changed_by: Optional[str]
    old_data:   Optional[dict[str, Any]]
    new_data:   Optional[dict[str, Any]]

    model_config = {"from_attributes": True}


# ── AI schemas ─────────────────────────────────────────────
class NLSearchRequest(BaseModel):
    question: str = Field(..., description="Natural language question about your events")

    model_config = {
        "json_schema_extra": {
            "example": {"question": "show me all failed logins from India"}
        }
    }


class NLSearchResponse(BaseModel):
    question:       str
    generated_sql:  str
    results:        list[dict[str, Any]]
    result_count:   int


class SummaryRequest(BaseModel):
    user_id:   Optional[int] = None
    limit:     int           = Field(default=20, ge=1, le=100)


class SummaryResponse(BaseModel):
    summary:     str
    events_used: int
