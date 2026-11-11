import re
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models import User, Profile
from backend.schemas import UserSignup, UserLogin, Token, UserOut, ProfileUpdate, PasswordChange
from backend.auth import get_password_hash, verify_password, create_user_token, get_current_user
from backend.cloudinary_service import upload_avatar, check_cloudinary_status
from backend.ratelimit import (
    login_limiter, signup_limiter, password_limiter, rate_limit
)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

EMAIL_REGEX = re.compile(r"^[\w\.-]+@([\w-]+\.)+[\w-]{2,63}$")

@router.post("/signup", response_model=Token, dependencies=[Depends(rate_limit(signup_limiter, "signup"))])
def signup(payload: UserSignup, db: Session = Depends(get_db)):
    clean_email = payload.email.strip().lower()
    clean_username = payload.username.strip().lower()

    if not EMAIL_REGEX.match(clean_email):
        raise HTTPException(status_code=400, detail="Invalid email format. Please provide an original, valid email.")

    if db.query(User).filter((User.email == clean_email) | (User.username == clean_username)).first():
        raise HTTPException(status_code=400, detail="Username or Email already registered.")

    hashed = get_password_hash(payload.password)
    user = User(
        email=clean_email,
        username=clean_username,
        hashed_password=hashed,
        full_name=payload.full_name.strip(),
        phone=payload.phone.strip() if payload.phone else None,
        is_sharing=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    profile = Profile(user_id=user.id)
    db.add(profile)
    db.commit()

    token = create_user_token(user)
    return {"access_token": token, "token_type": "bearer", "user": user}

@router.post("/login", response_model=Token, dependencies=[Depends(rate_limit(login_limiter, "login"))])
def login(payload: UserLogin, db: Session = Depends(get_db)):
    ident = payload.username_or_email.strip().lower()
    user = db.query(User).filter(
        (User.email == ident) | (User.username == ident)
    ).first()

    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    token = create_user_token(user)
    return {"access_token": token, "token_type": "bearer", "user": user}

@router.get("/me", response_model=UserOut)
def get_profile(current_user: User = Depends(get_current_user)):
    return current_user

@router.put("/profile", response_model=UserOut)
def update_profile(
    payload: ProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if payload.full_name:
        current_user.full_name = payload.full_name.strip()
    if payload.phone is not None:
        current_user.phone = payload.phone.strip()
    if payload.avatar_url is not None:
        if payload.avatar_url and (payload.avatar_url.startswith("data:image") or len(payload.avatar_url) > 500):
            current_user.avatar_url = upload_avatar(payload.avatar_url, current_user.id)
        elif payload.avatar_url == "" or payload.avatar_url == "__REMOVE__":
            current_user.avatar_url = None
        else:
            current_user.avatar_url = payload.avatar_url

    profile = current_user.profile or Profile(user_id=current_user.id)
    if payload.bio is not None:
        profile.bio = payload.bio.strip()
    if payload.home_address is not None:
        profile.home_address = payload.home_address.strip()
    if payload.blood_group is not None:
        profile.blood_group = payload.blood_group.strip()
    if payload.medical_notes is not None:
        profile.medical_notes = payload.medical_notes.strip()

    db.add(profile)
    db.commit()
    db.refresh(current_user)
    return current_user

@router.post("/upload-avatar")
async def upload_user_avatar(
    file: Optional[UploadFile] = File(None),
    avatar_base64: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Directly uploads an avatar file or base64 data to Cloudinary CDN and updates the user's profile.
    """
    image_data = None
    if file:
        file_bytes = await file.read()
        if len(file_bytes) > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File too large (maximum 10MB allowed)")
        image_data = file_bytes
    elif avatar_base64:
        image_data = avatar_base64
    else:
        raise HTTPException(status_code=400, detail="No file or image data provided.")

    cloudinary_url = upload_avatar(image_data, current_user.id)
    current_user.avatar_url = cloudinary_url
    db.commit()
    db.refresh(current_user)

    is_cloud = bool(cloudinary_url and "res.cloudinary.com" in cloudinary_url)
    return {
        "success": True,
        "avatar_url": current_user.avatar_url,
        "is_cloudinary": is_cloud,
        "message": "Avatar uploaded to Cloudinary CDN successfully!" if is_cloud else "Avatar saved successfully."
    }

@router.get("/cloudinary-status")
def get_cloudinary_status():
    """
    Check live Cloudinary configuration and connection status.
    """
    return check_cloudinary_status()

@router.post("/change-password", dependencies=[Depends(rate_limit(password_limiter, "password"))])
def change_password(
    payload: PasswordChange,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Securely updates the authenticated user's password.

    All previously issued tokens are invalidated. A fresh token is returned so
    the current session stays logged in.
    """
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    
    if len(payload.new_password) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters.")

    current_user.hashed_password = get_password_hash(payload.new_password)
    db.commit()
    db.refresh(current_user)
    return {
        "success": True,
        "message": "Password changed successfully!",
        "access_token": create_user_token(current_user),
        "token_type": "bearer",
    }