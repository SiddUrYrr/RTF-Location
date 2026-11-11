import re
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator


_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,50}$")
_INVITE_CODE_RE = re.compile(r"^[A-Fa-f0-9]{8}$")
_PHONE_RE = re.compile(r"^\+?[0-9\s\-()]{5,20}$")


def _clean(value: Optional[str], *, allow_angle: bool = True) -> Optional[str]:
    """Strip control characters / collapse whitespace; optionally block <>."""
    if value is None:
        return None
    cleaned = _CONTROL_CHARS.sub("", value).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not allow_angle and ("<" in cleaned or ">" in cleaned):
        raise ValueError("must not contain '<' or '>' characters")
    return cleaned


class ProfileOut(BaseModel):
    bio: Optional[str] = None
    home_address: Optional[str] = None
    blood_group: Optional[str] = None
    medical_notes: Optional[str] = None

    class Config:
        from_attributes = True

class UserOut(BaseModel):
    id: int
    email: str
    username: str
    full_name: str
    phone: Optional[str] = None
    avatar_url: Optional[str] = None
    is_sharing: bool
    sharing_expires_at: Optional[datetime] = None
    privacy_mode: str
    is_sos_active: bool
    last_active: datetime
    profile: Optional[ProfileOut] = None

    class Config:
        from_attributes = True

class UserSignup(BaseModel):
    email: str = Field(..., max_length=255)
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6, max_length=72)
    full_name: str = Field(..., min_length=1, max_length=100)
    phone: Optional[str] = Field(default=None, max_length=20)

    @field_validator("password")
    @classmethod
    def valid_password_bytes(cls, v: str) -> str:
        if len(v.encode("utf-8")) > 72:
            raise ValueError("password must be at most 72 bytes")
        return v

    @field_validator("email")
    @classmethod
    def clean_email(cls, v: str) -> str:
        return _clean(v) or ""

    @field_validator("username")
    @classmethod
    def valid_username(cls, v: str) -> str:
        v = (_clean(v) or "")
        if not _USERNAME_RE.match(v):
            raise ValueError("username may only contain letters, numbers and underscores (3-50 chars)")
        return v

    @field_validator("full_name")
    @classmethod
    def valid_full_name(cls, v: str) -> str:
        return _clean(v, allow_angle=False) or ""

    @field_validator("phone")
    @classmethod
    def valid_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not v.strip():
            return None
        v = (_clean(v) or "")
        if not _PHONE_RE.match(v):
            raise ValueError("invalid phone number")
        return v

class UserLogin(BaseModel):
    username_or_email: str = Field(..., max_length=255)
    password: str = Field(..., max_length=72)

class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserOut

class PasswordChange(BaseModel):
    current_password: str = Field(..., max_length=72)
    new_password: str = Field(..., min_length=6, max_length=72)

    @field_validator("new_password")
    @classmethod
    def valid_password_bytes(cls, v: str) -> str:
        if len(v.encode("utf-8")) > 72:
            raise ValueError("password must be at most 72 bytes")
        return v

class ProfileUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, max_length=100)
    phone: Optional[str] = Field(default=None, max_length=20)
    avatar_url: Optional[str] = Field(default=None, max_length=2_000_000)
    bio: Optional[str] = Field(default=None, max_length=255)
    home_address: Optional[str] = Field(default=None, max_length=255)
    blood_group: Optional[str] = Field(default=None, max_length=10)
    medical_notes: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("full_name")
    @classmethod
    def valid_full_name(cls, v: Optional[str]) -> Optional[str]:
        return _clean(v, allow_angle=False) if v is not None else None

    @field_validator("phone")
    @classmethod
    def valid_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not v.strip():
            return None
        v = (_clean(v) or "")
        if not _PHONE_RE.match(v):
            raise ValueError("invalid phone number")
        return v

    @field_validator("avatar_url")
    @classmethod
    def valid_avatar_url(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "" or v == "__REMOVE__":
            return v
        allowed = (
            v.startswith("data:image/")
            or v.startswith("http://")
            or v.startswith("https://")
            or v.startswith("/")
        )
        if not allowed:
            raise ValueError("avatar_url must be an http(s) URL or data:image payload")
        return v

    @field_validator("bio", "home_address", "blood_group", "medical_notes")
    @classmethod
    def clean_text(cls, v: Optional[str]) -> Optional[str]:
        return _clean(v) if v is not None else None

class LocationUpdate(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    accuracy: Optional[float] = Field(default=None, ge=0, le=100_000)
    speed: Optional[float] = Field(default=None, ge=0, le=1000)
    heading: Optional[float] = Field(default=None, ge=0, le=360)
    battery_level: Optional[int] = Field(default=None, ge=0, le=100)
    is_sos: Optional[bool] = False

class LocationBatchSync(BaseModel):
    locations: List[LocationUpdate] = Field(..., max_length=500)

class SharingToggleRequest(BaseModel):
    is_sharing: bool
    duration_minutes: Optional[int] = Field(default=None, ge=0, le=525600)
    privacy_mode: Optional[str] = Field(default="exact", pattern="^(exact|blurred)$")

class FriendRequestCreate(BaseModel):
    username_or_email: str = Field(..., min_length=1, max_length=255)

class GroupCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    description: Optional[str] = Field(default=None, max_length=255)

    @field_validator("name")
    @classmethod
    def valid_name(cls, v: str) -> str:
        return _clean(v, allow_angle=False) or ""

    @field_validator("description")
    @classmethod
    def valid_description(cls, v: Optional[str]) -> Optional[str]:
        return _clean(v, allow_angle=False) if v is not None else None

class GroupJoin(BaseModel):
    invite_code: str = Field(..., min_length=8, max_length=8)

    @field_validator("invite_code")
    @classmethod
    def valid_code(cls, v: str) -> str:
        v = (_clean(v) or "")
        if not _INVITE_CODE_RE.match(v):
            raise ValueError("invalid invite code")
        return v

class EmergencyContactCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    phone: str = Field(..., max_length=20)
    relationship: str = Field(..., min_length=1, max_length=50)
    notify_in_app: bool = True

    @field_validator("name", "relationship")
    @classmethod
    def valid_display_text(cls, v: str) -> str:
        return _clean(v, allow_angle=False) or ""

    @field_validator("phone")
    @classmethod
    def valid_phone(cls, v: str) -> str:
        v = (_clean(v) or "")
        if not _PHONE_RE.match(v):
            raise ValueError("invalid phone number")
        return v

class SOSAlertRequest(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    message: Optional[str] = Field(default="Emergency! I need assistance.", max_length=200)

    @field_validator("message")
    @classmethod
    def clean_message(cls, v: Optional[str]) -> Optional[str]:
        return _clean(v) if v is not None else None
