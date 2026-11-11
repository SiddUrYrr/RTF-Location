import hashlib
import hmac
import math
from datetime import timedelta
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc
from backend.database import get_db
from backend.models import User, Location, Friend, GroupMember
from backend.schemas import LocationUpdate, LocationBatchSync, SharingToggleRequest
from backend.auth import get_current_user, SECRET_KEY
from backend.timeutils import utcnow

router = APIRouter(prefix="/api/locations", tags=["Location Sharing"])

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2.0)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2.0)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(R * c, 2)


def blurred_point(user_id: int, latitude: float, longitude: float) -> tuple[float, float]:
    """
    Deterministically shift a user's coordinates by 180-300 m in a random direction.

    The offset is derived from the app secret + user id, so:
      - the marker stays put instead of teleporting on every GPS update
      - a user's blurred route keeps its shape (the whole trail is shifted once)
      - averaging many readings cannot recover the true point, because the
        unknown offset is constant rather than zero-mean noise
      - nobody can reproduce the original coordinate without the secret
    """
    digest = hmac.new(
        SECRET_KEY.encode("utf-8"),
        f"blur:{user_id}".encode("utf-8"),
        hashlib.sha256,
    ).digest()
    angle = (int.from_bytes(digest[0:4], "big") / 2**32) * 2 * math.pi
    distance_m = 180.0 + 120.0 * (int.from_bytes(digest[4:8], "big") / (2**32 - 1))

    dlat = (distance_m * math.cos(angle)) / 111_320.0
    cos_lat = math.cos(math.radians(latitude)) or 1e-6
    dlng = (distance_m * math.sin(angle)) / (111_320.0 * cos_lat)
    return round(latitude + dlat, 6), round(longitude + dlng, 6)

@router.post("/update")
def update_location(
    payload: LocationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not current_user.is_sharing and not payload.is_sos:
        return {"status": "skipped", "message": "Sharing is disabled"}

    loc = Location(
        user_id=current_user.id,
        latitude=payload.latitude,
        longitude=payload.longitude,
        accuracy=payload.accuracy,
        speed=payload.speed,
        heading=payload.heading,
        battery_level=payload.battery_level,
        is_sos=bool(payload.is_sos),
        timestamp=utcnow()
    )
    db.add(loc)
    current_user.last_active = utcnow()
    db.commit()
    return {"status": "success", "id": loc.id}

@router.post("/batch-sync")
def sync_offline_locations(
    payload: LocationBatchSync,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    count = 0
    for item in payload.locations:
        loc = Location(
            user_id=current_user.id,
            latitude=item.latitude,
            longitude=item.longitude,
            accuracy=item.accuracy,
            battery_level=item.battery_level,
            timestamp=utcnow()
        )
        db.add(loc)
        count += 1
    current_user.last_active = utcnow()
    db.commit()
    return {"status": "synced", "count": count}

@router.post("/toggle-sharing")
def toggle_sharing(
    payload: SharingToggleRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    current_user.is_sharing = payload.is_sharing
    current_user.privacy_mode = payload.privacy_mode or "exact"
    db.commit()
    return {"is_sharing": current_user.is_sharing, "privacy_mode": current_user.privacy_mode}

@router.get("/live-feed")
def get_live_family_locations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    friend_ids = [f.friend_id for f in db.query(Friend).filter(Friend.user_id == current_user.id).all()]
    my_groups = [m.group_id for m in db.query(GroupMember).filter(GroupMember.user_id == current_user.id).all()]
    group_member_ids = [gm.user_id for gm in db.query(GroupMember).filter(GroupMember.group_id.in_(my_groups)).all()] if my_groups else []

    all_ids = set(friend_ids + group_member_ids)
    all_ids.discard(current_user.id)

    my_loc = db.query(Location).filter(Location.user_id == current_user.id).order_by(desc(Location.timestamp)).first()
    feed = []

    for uid in all_ids:
        u = db.query(User).filter(User.id == uid).first()
        if not u:
            continue

        latest = db.query(Location).filter(Location.user_id == uid).order_by(desc(Location.timestamp)).first()
        if not latest or (not u.is_sharing and not u.is_sos_active):
            feed.append({
                "user_id": u.id,
                "username": u.username,
                "full_name": u.full_name,
                "avatar_url": u.avatar_url,
                "is_sharing": False,
                "is_sos": bool(u.is_sos_active),
                "location": None,
                "distance_km": None
            })
            continue

        lat, lng = latest.latitude, latest.longitude
        if u.privacy_mode == "blurred" and not u.is_sos_active:
            lat, lng = blurred_point(u.id, lat, lng)

        distance = None
        if my_loc:
            distance = haversine_km(my_loc.latitude, my_loc.longitude, lat, lng)

        feed.append({
            "user_id": u.id,
            "username": u.username,
            "full_name": u.full_name,
            "avatar_url": u.avatar_url,
            "is_sharing": u.is_sharing,
            "is_sos": bool(u.is_sos_active),
            "distance_km": distance,
            "location": {
                "latitude": lat,
                "longitude": lng,
                "battery_level": latest.battery_level,
                "timestamp": latest.timestamp
            }
        })

    return feed

@router.get("/history/{user_id}")
def get_location_history(
    user_id: int,
    hours: int = Query(default=24, ge=1, le=168),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Verify authorization (Must be self, mutual friend, or in the same circle)
    if user_id != current_user.id:
        is_friend = db.query(Friend).filter(Friend.user_id == current_user.id, Friend.friend_id == user_id).first()
        my_groups = [m.group_id for m in db.query(GroupMember).filter(GroupMember.user_id == current_user.id).all()]
        in_same_group = None
        if my_groups:
            in_same_group = db.query(GroupMember).filter(GroupMember.group_id.in_(my_groups), GroupMember.user_id == user_id).first()
        
        if not is_friend and not in_same_group:
            raise HTTPException(status_code=403, detail="Unauthorized: You can only view location history for verified circle members.")

    subject = db.query(User).filter(User.id == user_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="User not found.")

    # Never expose exact history for a user who has blurred mode enabled.
    # Owners can still see their own exact trail; active SOS overrides blur.
    hide_exact = (
        user_id != current_user.id
        and subject.privacy_mode == "blurred"
        and not subject.is_sos_active
    )

    since = utcnow() - timedelta(hours=hours)
    trail = db.query(Location).filter(
        Location.user_id == user_id,
        Location.timestamp >= since
    ).order_by(Location.timestamp.asc()).all()

    points = []
    for l in trail:
        lat, lng = l.latitude, l.longitude
        if hide_exact:
            lat, lng = blurred_point(user_id, lat, lng)
        points.append({
            "latitude": lat,
            "longitude": lng,
            "timestamp": l.timestamp.strftime("%I:%M %p, %d %b") if l.timestamp else "",
            "battery_level": l.battery_level
        })
    return points