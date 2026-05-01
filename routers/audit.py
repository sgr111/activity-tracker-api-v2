from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address

from database import get_db
from models import EventAudit
from schemas import AuditResponse

router  = APIRouter(prefix="/audit", tags=["Audit / CDC"])
limiter = Limiter(key_func=get_remote_address)


# ── GET /audit ─────────────────────────────────────────────
@router.get("/", response_model=list[AuditResponse])
@limiter.limit("20/minute")
async def list_audit(
    request:   Request,
    operation: str | None = None,
    limit:     int        = 50,
    db:        Session    = Depends(get_db)
):
    """
    View the CDC audit trail.
    Optionally filter by operation: INSERT, UPDATE, DELETE.
    """
    query = db.query(EventAudit)
    if operation:
        query = query.filter(EventAudit.operation == operation.upper())
    return query.order_by(EventAudit.changed_at.desc()).limit(limit).all()


# ── GET /audit/{event_id} ──────────────────────────────────
@router.get("/event/{event_id}", response_model=list[AuditResponse])
@limiter.limit("20/minute")
async def audit_for_event(
    request:  Request,
    event_id: int,
    db:       Session = Depends(get_db)
):
    """
    View the full CDC history for a specific event ID.
    Shows all inserts, updates, and deletes for that record.
    """
    rows = (
        db.query(EventAudit)
        .filter(
            (EventAudit.new_data["id"].astext == str(event_id)) |
            (EventAudit.old_data["id"].astext == str(event_id))
        )
        .order_by(EventAudit.changed_at.asc())
        .all()
    )
    return rows
