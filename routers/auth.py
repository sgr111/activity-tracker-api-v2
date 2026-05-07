from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address

from database import get_db
from models import User
from schemas import UserCreate, UserResponse, Token, LoginRequest
from services.auth_service import (
    hash_password, verify_password,
    create_access_token, get_current_user
)

router  = APIRouter(prefix="/auth", tags=["Auth"])
limiter = Limiter(key_func=get_remote_address)


# ── POST /auth/register ────────────────────────────────────
@router.post("/register", response_model=UserResponse, status_code=201)
@limiter.limit("5/minute")
async def register(
    request: Request,
    body:    UserCreate,
    db:      Session = Depends(get_db)
):
    """Register a new user account."""
    existing = db.query(User).filter(User.email == body.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    user = User(
        email           = body.email,
        hashed_password = hash_password(body.password)
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ── POST /auth/login ───────────────────────────────────────
@router.post("/login", response_model=Token)
@limiter.limit("10/minute")
async def login(
    request: Request,
    body:    LoginRequest,
    db:      Session = Depends(get_db)
):
    """Login and receive a JWT access token."""
    user = db.query(User).filter(User.email == body.email).first()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Inactive user")

    token = create_access_token(data={"sub": user.email})
    return Token(access_token=token, token_type="bearer")


# ── GET /auth/me ───────────────────────────────────────────
@router.get("/me", response_model=UserResponse)
@limiter.limit("30/minute")
async def me(
    request:      Request,
    current_user: User = Depends(get_current_user)
):
    """Get the currently authenticated user's profile."""
    return current_user
