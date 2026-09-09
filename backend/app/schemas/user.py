# CareerMind AI User Schemas
from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional

# ---- Auth ----
class UserRegisterRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=255, description="User email")
    username: str = Field(..., min_length=3, max_length=100, description="Username")
    password: str = Field(..., min_length=6, max_length=100, description="Password")

class UserLoginRequest(BaseModel):
    username: str = Field(..., description="Username or email")
    password: str = Field(..., min_length=1, description="Password")

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    username: str

# ---- User Profile ----
class UserProfileResponse(BaseModel):
    id: str
    email: str
    username: str
    full_name: Optional[str] = None
    phone: Optional[str] = None
    avatar_url: Optional[str] = None
    bio: Optional[str] = None
    career_goal: Optional[str] = None
    target_industry: Optional[str] = None
    years_of_experience: Optional[int] = None
    current_level: Optional[str] = None
    is_active: bool
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}

class UserProfileUpdateRequest(BaseModel):
    full_name: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)
    avatar_url: Optional[str] = Field(None, max_length=500)
    bio: Optional[str] = None
    career_goal: Optional[str] = Field(None, max_length=255)
    target_industry: Optional[str] = Field(None, max_length=100)
    years_of_experience: Optional[int] = Field(None, ge=0, le=50)
    current_level: Optional[str] = Field(None, max_length=50)
