from pydantic import BaseModel, Field
from typing import Any, Optional
from datetime import datetime


class EventCreate(BaseModel):
    user_id:    int
    event_type: str
    payload:    dict[str, Any] = Field(default_factory=dict)

    model_config = {
        "json_schema_extra": {
            "example": {
                "user_id":    1,
                "event_type": "login",
                "payload": {
                    "ip":      "192.168.1.1",
                    "country": "IN",
                    "device":  "mobile",
                    "status":  "success"
                }
            }
        }
    }


class EventUpdate(BaseModel):
    event_type: Optional[str]            = None
    payload:    Optional[dict[str, Any]] = None


class EventResponse(BaseModel):
    id:         int
    user_id:    int
    owner_id:   Optional[int]
    event_type: str
    payload:    dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class NLSearchRequest(BaseModel):
    question: str = Field(..., description="Natural language question about your events")

    model_config = {
        "json_schema_extra": {
            "example": {"question": "show me all failed logins from India"}
        }
    }


class NLSearchResponse(BaseModel):
    question:      str
    generated_sql: str
    results:       list[dict[str, Any]]
    result_count:  int


class SummaryRequest(BaseModel):
    user_id: Optional[int] = None
    limit:   int           = Field(default=20, ge=1, le=100)


class SummaryResponse(BaseModel):
    summary:     str
    events_used: int


# ── Phase 2c/3a — Semantic Search ─────────────────────────
class SemanticSearchRequest(BaseModel):
    query: str  = Field(..., description="Natural language query to find similar events")
    limit: int  = Field(default=5, ge=1, le=20)

    model_config = {
        "json_schema_extra": {
            "example": {
                "query": "user had trouble logging in",
                "limit": 5
            }
        }
    }


class SemanticSearchResult(BaseModel):
    id:         int
    user_id:    int
    owner_id:   Optional[int]
    event_type: str
    payload:    dict[str, Any]
    created_at: datetime
    similarity: float


class SemanticSearchResponse(BaseModel):
    query:        str
    results:      list[SemanticSearchResult]
    result_count: int