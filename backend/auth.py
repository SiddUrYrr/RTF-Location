import hashlib
import logging
import os
import secrets
from datetime import datetime, timedelta
from typing import Optional
from dotenv import load_dotenv
import bcrypt
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models import User
from backend.timeutils import utcnow

load_dotenv()

_logger = logging.getLogger("rtf.auth")

SECRET_KEY = os.getenv("SECRET_KEY", "").strip()
if not SECRET_KEY:
    # Never fall back to a known/hardcoded key. A random per-process key means
    # tokens are invalidated on restart, which is far safer than a public default.
    SECRET_KEY = secrets.token_urlsafe(48)
    _logger.warning(
        "SECRET_KEY is not set. Generated an ephemeral key; sessions will not "
        "survive a restart. Add SECRET_KEY to your .env file."
    )

ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "10080"))

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def password_fingerprint(hashed_password: str) -> str:
    """
    Short fingerprint of the current password hash, embedded in every JWT.

    Changing the password changes the hash, so all previously issued tokens
    stop validating immediately (no schema change needed).
    """
    return hashlib.sha256(hashed_password.encode("utf-8")).hexdigest()[:16]


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    pwd_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_user_token(user: User) -> str:
    return create_access_token(
        {"sub": str(user.id), "pv": password_fingerprint(user.hashed_password)}
    )


def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials or session expired.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_exception
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.id == int(user_id)).first()
    if user is None or not user.is_active:
        raise credentials_exception

    # Reject tokens issued before a password change / hash rotation.
    if payload.get("pv") != password_fingerprint(user.hashed_password):
        raise credentials_exception

    now = utcnow()
    if not user.last_active or (now - user.last_active).total_seconds() > 120:
        user.last_active = now
        db.commit()
    return user
