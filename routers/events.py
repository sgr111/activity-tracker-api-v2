from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import text
from slowapi import Limiter
from slowapi.util import get_remote_address
import httpx

from database import get_db
from models import Event
from schemas import (
    EventCreate, EventUpdate, EventResponse,
    NLSearchRequest, NLSearchResponse,
    SummaryRequest, SummaryResponse
)
from services.enrichment import enrich_event
from services.ai_service import natural_language_to_sql, summarise_events

router  = APIRouter(prefix="/events", tags=["Events"])
limiter = Limiter(key_func=get_remote_address)


# ── POST /events ───────────────────────────────────────────
@router.post("/", response_model=EventResponse, status_code=201)
@limiter.limit("10/minute")
async def create_event(
    request: Request,
    body:    EventCreate,
    db:      Session = Depends(get_db)
):
    """Log a new activity event. Payload is enriched via httpx before saving."""
    async with httpx.AsyncClient() as client:
        enriched_payload = await enrich_event(client, body.payload)

    event = Event(
        user_id    = body.user_id,
        event_type = body.event_type,
        payload    = enriched_payload
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


# ── GET /events ────────────────────────────────────────────
@router.get("/", response_model=list[EventResponse])
@limiter.limit("30/minute")
async def list_events(
    request:    Request,
    user_id:    int  | None = None,
    event_type: str  | None = None,
    country:    str  | None = None,
    limit:      int         = 20,
    db:         Session     = Depends(get_db)
):
    """List events with optional filters. Supports JSONB payload filtering."""
    query = db.query(Event)

    if user_id:
        query = query.filter(Event.user_id == user_id)
    if event_type:
        query = query.filter(Event.event_type == event_type)
    if country:
        query = query.filter(Event.payload["country"].astext == country)

    return query.order_by(Event.created_at.desc()).limit(limit).all()


# ── GET /events/{id} ───────────────────────────────────────
@router.get("/{event_id}", response_model=EventResponse)
@limiter.limit("30/minute")
async def get_event(
    request:  Request,
    event_id: int,
    db:       Session = Depends(get_db)
):
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


# ── PUT /events/{id} ───────────────────────────────────────
@router.put("/{event_id}", response_model=EventResponse)
@limiter.limit("10/minute")
async def update_event(
    request:  Request,
    event_id: int,
    body:     EventUpdate,
    db:       Session = Depends(get_db)
):
    """Update an event. CDC trigger will automatically log the change."""
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    if body.event_type is not None:
        event.event_type = body.event_type
    if body.payload is not None:
        event.payload = {**event.payload, **body.payload}

    db.commit()
    db.refresh(event)
    return event


# ── DELETE /events/{id} ────────────────────────────────────
@router.delete("/{event_id}", status_code=204)
@limiter.limit("5/minute")
async def delete_event(
    request:  Request,
    event_id: int,
    db:       Session = Depends(get_db)
):
    """Delete an event. CDC trigger will log the deleted record in audit."""
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    db.delete(event)
    db.commit()


# ── POST /events/ai/search ─────────────────────────────────
@router.post("/ai/search", response_model=NLSearchResponse)
@limiter.limit("10/minute")
async def nl_search(
    request: Request,
    body:    NLSearchRequest,
    db:      Session = Depends(get_db)
):
    """
    Natural language search powered by Gemini.
    Ask questions like: 'show me failed logins from India'
    Gemini converts it to SQL, we run it, return results.
    """
    try:
        sql = await natural_language_to_sql(body.question)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Gemini error: {str(e)}")

    try:
        rows = db.execute(text(sql)).fetchall()
        results = [dict(r._mapping) for r in rows]
    except Exception as e:
        raise HTTPException(
            status_code=422,
            detail=f"Generated SQL failed: {str(e)} | SQL: {sql}"
        )

    return NLSearchResponse(
        question      = body.question,
        generated_sql = sql,
        results       = results,
        result_count  = len(results)
    )


# ── POST /events/ai/summary ────────────────────────────────
@router.post("/ai/summary", response_model=SummaryResponse)
@limiter.limit("5/minute")
async def summarise(
    request: Request,
    body:    SummaryRequest,
    db:      Session = Depends(get_db)
):
    """
    AI-powered summary of recent events using Gemini.
    Optionally filter by user_id.
    """
    query = db.query(Event)
    if body.user_id:
        query = query.filter(Event.user_id == body.user_id)

    events = query.order_by(Event.created_at.desc()).limit(body.limit).all()

    events_data = [
        {
            "id":         e.id,
            "user_id":    e.user_id,
            "event_type": e.event_type,
            "payload":    e.payload,
            "created_at": str(e.created_at)
        }
        for e in events
    ]

    try:
        summary = await summarise_events(events_data)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Gemini error: {str(e)}")

    return SummaryResponse(summary=summary, events_used=len(events_data))
