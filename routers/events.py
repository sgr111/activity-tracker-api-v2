from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import text
from slowapi import Limiter
import httpx
import json

from database import get_db
from database_async import get_async_conn
from models import Event, User
from schemas import (
    EventCreate, EventUpdate, EventResponse,
    NLSearchRequest, NLSearchResponse,
    SummaryRequest, SummaryResponse,
    SemanticSearchRequest, SemanticSearchResponse, SemanticSearchResult
)
from services.enrichment import enrich_event
from services.ai_service import (
    natural_language_to_sql, summarise_events,
    embed_text, event_to_text
)
from services.auth_service import get_current_user, get_user_id_for_limit

router  = APIRouter(prefix="/events", tags=["Events"])
limiter = Limiter(key_func=get_user_id_for_limit)


# ── POST /events ───────────────────────────────────────────
@router.post("/", response_model=EventResponse, status_code=201)
@limiter.limit("10/minute")
async def create_event(
    request:      Request,
    body:         EventCreate,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user)
):
    """Log a new activity event. Payload enriched via httpx. Embedding generated for semantic search."""
    async with httpx.AsyncClient() as client:
        enriched_payload = await enrich_event(client, body.payload)

    # Generate embedding for semantic search
    event_text = event_to_text(body.event_type, enriched_payload)
    embedding  = await embed_text(event_text)

    event = Event(
        user_id    = body.user_id,
        owner_id   = current_user.id,
        event_type = body.event_type,
        payload    = enriched_payload,
        embedding  = embedding
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


# ── GET /events ────────────────────────────────────────────
@router.get("/", response_model=list[EventResponse])
@limiter.limit("30/minute")
async def list_events(
    request:      Request,
    user_id:      int  | None = None,
    event_type:   str  | None = None,
    country:      str  | None = None,
    limit:        int         = 20,
    db:           Session     = Depends(get_db),
    current_user: User        = Depends(get_current_user)
):
    """List your events with optional filters."""
    query = db.query(Event).filter(Event.owner_id == current_user.id)

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
    request:      Request,
    event_id:     int,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user)
):
    event = db.query(Event).filter(
        Event.id       == event_id,
        Event.owner_id == current_user.id
    ).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


# ── PUT /events/{id} ───────────────────────────────────────
@router.put("/{event_id}", response_model=EventResponse)
@limiter.limit("10/minute")
async def update_event(
    request:      Request,
    event_id:     int,
    body:         EventUpdate,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user)
):
    """Update your event. CDC trigger logs the change."""
    event = db.query(Event).filter(
        Event.id       == event_id,
        Event.owner_id == current_user.id
    ).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    if body.event_type is not None:
        event.event_type = body.event_type
    if body.payload is not None:
        event.payload = {**event.payload, **body.payload}

    # Regenerate embedding on update
    event_text     = event_to_text(event.event_type, event.payload)
    event.embedding = await embed_text(event_text)

    db.commit()
    db.refresh(event)
    return event


# ── DELETE /events/{id} ────────────────────────────────────
@router.delete("/{event_id}", status_code=204)
@limiter.limit("5/minute")
async def delete_event(
    request:      Request,
    event_id:     int,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user)
):
    """Delete your event. CDC trigger logs the deletion."""
    event = db.query(Event).filter(
        Event.id       == event_id,
        Event.owner_id == current_user.id
    ).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    db.delete(event)
    db.commit()


# ── POST /events/ai/search ─────────────────────────────────
@router.post("/ai/search", response_model=NLSearchResponse)
@limiter.limit("10/minute")
async def nl_search(
    request:      Request,
    body:         NLSearchRequest,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user)
):
    """Natural language search powered by Gemini — converts question to SQL."""
    try:
        sql = await natural_language_to_sql(body.question)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Gemini error: {str(e)}")

    try:
        rows    = db.execute(text(sql)).fetchall()
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
    request:      Request,
    body:         SummaryRequest,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user)
):
    """AI-powered summary of your recent events using Gemini."""
    query = db.query(Event).filter(Event.owner_id == current_user.id)
    if body.user_id:
        query = query.filter(Event.user_id == body.user_id)

    events      = query.order_by(Event.created_at.desc()).limit(body.limit).all()
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


# ── POST /events/ai/semantic ───────────────────────────────
@router.post("/ai/semantic", response_model=SemanticSearchResponse)
@limiter.limit("10/minute")
async def semantic_search(
    request:      Request,
    body:         SemanticSearchRequest,
    conn          = Depends(get_async_conn),
    current_user: User = Depends(get_current_user)
):
    """
    Semantic search using pgvector cosine similarity.
    Finds events similar in MEANING to your query,
    even if the exact words don't match.
    e.g. 'user had trouble logging in' finds events with status:failed
    """
    try:
        query_embedding = await embed_text(body.query)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Embedding error: {str(e)}")

    # pgvector <=> = cosine distance (lower = more similar)
    # 1 - distance = similarity score
    sql = """
        SELECT
            id,
            user_id,
            owner_id,
            event_type,
            payload,
            created_at,
            1 - (embedding <=> $1::vector) AS similarity
        FROM events
        WHERE owner_id = $2
          AND embedding IS NOT NULL
        ORDER BY embedding <=> $1
        LIMIT $3
    """
    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

    rows = await conn.fetch(
        sql,
        embedding_str,
        current_user.id,
        body.limit
    )

    results = [
        SemanticSearchResult(
            id         = row["id"],
            user_id    = row["user_id"],
            owner_id   = row["owner_id"],
            event_type = row["event_type"],
            payload    = json.loads(row["payload"]) if isinstance(row["payload"], str) else dict(row["payload"]),
            created_at = row["created_at"],
            similarity = round(float(row["similarity"]), 4)
        )
        for row in rows
    ]

    return SemanticSearchResponse(
        query        = body.query,
        results      = results,
        result_count = len(results)
    )