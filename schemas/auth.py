from pydantic import BaseModel
from datetime import datetime


class UserCreate(BaseModel):
    email:    str
    password: str

    model_config = {
        "json_schema_extra": {
            "example": {
                "email":    "user@example.com",
                "password": "strongpassword123"
            }
        }
    }


class UserResponse(BaseModel):
    id:         int
    email:      str
    is_active:  bool
    created_at: datetime

    model_config = {"from_attributes": True}


class Token(BaseModel):
    access_token: str
    token_type:   str


class LoginRequest(BaseModel):
    email:    str
    password: str

    model_config = {
        "json_schema_extra": {
            "example": {
                "email":    "user@example.com",
                "password": "strongpassword123"
            }
        }
    }
