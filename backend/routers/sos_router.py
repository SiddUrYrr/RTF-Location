from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import User, Location, Notification, Friend, GroupMember, EmergencyContact
from backend.schemas import SOSAlertRequest, EmergencyContactCreate
from backend.auth import get_current_user
from backend.ratelimit import sos_limiter, rate_limit
from backend.sms_service import escalate_sos_to_phones, sms_configured
from backend.timeutils import utcnow

router = APIRouter(prefix="/api/emergency", tags=["Emergency SOS"])


def _circle_recipient_ids(db: Session, user_id: int) -> set[int]:
    friend_ids = [f.friend_id for f in db.query(Friend).filter(Friend.user_id == user_id).all()]
    my_groups = [m.group_id for m in db.query(GroupMember).filter(GroupMember.user_id == user_id).all()]
    group_member_ids = [
        gm.user_id
        for gm in db.query(GroupMember).filter(GroupMember.group_id.in_(my_groups)).all()
    ] if my_groups else []
    recipients = set(friend_ids + group_member_ids)
    recipients.discard(user_id)
    return recipients


@router.get("/contacts")
def list_emergency_contacts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    contacts = (
        db.query(EmergencyContact)
        .filter(EmergencyContact.user_id == current_user.id)
        .order_by(EmergencyContact.created_at.asc())
        .all()
    )
    return [
        {
            "id": c.id,
            "name": c.name,
            "phone": c.phone,
            "relationship": c.relationship,
            "notify_in_app": c.notify_in_app,
        }
        for c in contacts
    ]


@router.post("/contacts")
def create_emergency_contact(
    payload: EmergencyContactCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    existing = db.query(EmergencyContact).filter(EmergencyContact.user_id == current_user.id).count()
    if existing >= 10:
        raise HTTPException(status_code=400, detail="You can add up to 10 emergency contacts.")

    contact = EmergencyContact(
        user_id=current_user.id,
        name=payload.name,
        phone=payload.phone,
        relationship=payload.relationship,
        notify_in_app=payload.notify_in_app,
    )
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return {
        "id": contact.id,
        "name": contact.name,
        "phone": contact.phone,
        "relationship": contact.relationship,
        "notify_in_app": contact.notify_in_app,
    }


@router.delete("/contacts/{contact_id}")
def delete_emergency_contact(
    contact_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    contact = db.query(EmergencyContact).filter(
        EmergencyContact.id == contact_id,
        EmergencyContact.user_id == current_user.id,
    ).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Emergency contact not found.")
    db.delete(contact)
    db.commit()
    return {"success": True, "message": "Emergency contact removed."}


@router.post("/sos/trigger", dependencies=[Depends(rate_limit(sos_limiter, "sos"))])
def trigger_sos(
    payload: SOSAlertRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    current_user.is_sos_active = True
    current_user.is_sharing = True

    loc = Location(
        user_id=current_user.id,
        latitude=payload.latitude,
        longitude=payload.longitude,
        is_sos=True,
        timestamp=utcnow()
    )
    db.add(loc)

    for r_id in _circle_recipient_ids(db, current_user.id):
        db.add(Notification(
            user_id=r_id,
            sender_id=current_user.id,
            type="SOS_ALERT",
            title="EMERGENCY SOS ALERT!",
            message=f"{current_user.full_name} triggered an SOS emergency signal!"
        ))

    contacts = db.query(EmergencyContact).filter(
        EmergencyContact.user_id == current_user.id
    ).all()
    phones = [c.phone for c in contacts if c.phone]
    user_name = current_user.full_name
    db.commit()

    # SMS escalation must never block the SOS response. The session is closed
    # by the time this runs, so only plain values are handed to the task.
    if phones and sms_configured():
        background_tasks.add_task(
            escalate_sos_to_phones,
            phones,
            user_name,
            payload.latitude,
            payload.longitude,
        )

    return {
        "status": "sos_active",
        "message": "Emergency SOS broadcasted!",
        "sms_contacts": len(phones),
        "sms_configured": sms_configured(),
    }


@router.post("/sos/resolve")
def resolve_sos(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    current_user.is_sos_active = False

    # Clear is_sos flag on recent locations to avoid stuck state
    recent_sos = db.query(Location).filter(Location.user_id == current_user.id, Location.is_sos == True).all()
    for l in recent_sos:
        l.is_sos = False

    for r_id in _circle_recipient_ids(db, current_user.id):
        db.add(Notification(
            user_id=r_id,
            sender_id=current_user.id,
            type="SOS_RESOLVED",
            title="Emergency Resolved",
            message=f"{current_user.full_name} marked themselves as SAFE."
        ))

    db.commit()
    return {"status": "resolved", "message": "SOS mode turned off. Returned to normal."}
