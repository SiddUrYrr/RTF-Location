from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc
from backend.database import get_db
from backend.models import Notification
from backend.auth import get_current_user

router = APIRouter(prefix="/api/notifications", tags=["Notifications"])

@router.get("/")
def get_notifications(db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    notifs = db.query(Notification).filter(
        Notification.user_id == current_user.id
    ).order_by(desc(Notification.created_at)).limit(30).all()

    return [{
        "id": n.id,
        "title": n.title,
        "message": n.message,
        "is_read": n.is_read
    } for n in notifs]

@router.delete("/clear")
@router.post("/clear")
def clear_all_notifications(db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    """Clean / delete all notifications for the logged-in user."""
    db.query(Notification).filter(Notification.user_id == current_user.id).delete()
    db.commit()
    return {"status": "success", "message": "All notifications cleared"}

@router.delete("/{notification_id}")
def delete_single_notification(notification_id: int, db: Session = Depends(get_db), current_user = Depends(get_current_user)):
    """Delete a single notification by ID."""
    notif = db.query(Notification).filter(
        Notification.id == notification_id,
        Notification.user_id == current_user.id
    ).first()
    if notif:
        db.delete(notif)
        db.commit()
    return {"status": "success", "message": "Notification deleted"}