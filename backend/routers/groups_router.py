import secrets
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc
from backend.database import get_db
from backend.models import User, FamilyGroup, GroupMember, Location, Notification
from backend.schemas import GroupCreate, GroupJoin
from backend.auth import get_current_user
from backend.ratelimit import join_limiter, rate_limit

router = APIRouter(prefix="/api/groups", tags=["Family Groups"])

@router.post("/create")
def create_group(
    payload: GroupCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    name = payload.name.strip()
    if len(name) < 2:
        raise HTTPException(status_code=400, detail="Circle name must be at least 2 characters.")

    code = secrets.token_hex(4).upper()
    while db.query(FamilyGroup).filter(FamilyGroup.invite_code == code).first():
        code = secrets.token_hex(4).upper()

    group = FamilyGroup(
        name=name,
        description=payload.description.strip() if payload.description else None,
        invite_code=code,
        created_by_id=current_user.id
    )
    db.add(group)
    db.flush()

    db.add(GroupMember(group_id=group.id, user_id=current_user.id, role="admin"))
    db.commit()
    db.refresh(group)
    return {"id": group.id, "name": group.name, "invite_code": group.invite_code, "member_count": 1}

@router.post("/join", dependencies=[Depends(rate_limit(join_limiter, "group-join"))])
def join_group(
    payload: GroupJoin,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    code = payload.invite_code.strip().upper()
    if not code:
        raise HTTPException(status_code=400, detail="Please enter an invite code.")

    group = db.query(FamilyGroup).filter(FamilyGroup.invite_code == code).first()
    if not group:
        raise HTTPException(status_code=404, detail="Invalid invite code. Circle not found.")

    if db.query(GroupMember).filter(GroupMember.group_id == group.id, GroupMember.user_id == current_user.id).first():
        raise HTTPException(status_code=400, detail="You are already a member of this circle.")

    db.add(GroupMember(group_id=group.id, user_id=current_user.id, role="member"))
    db.commit()
    return {"message": f"Successfully joined circle '{group.name}'!"}

@router.get("/")
def get_user_groups(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    memberships = db.query(GroupMember).filter(GroupMember.user_id == current_user.id).all()
    groups = []
    for m in memberships:
        g = m.group
        if not g:
            continue
        member_count = db.query(GroupMember).filter(GroupMember.group_id == g.id).count()
        groups.append({
            "id": g.id,
            "name": g.name,
            "invite_code": g.invite_code,
            "member_count": member_count,
            "role": m.role
        })
    return groups

@router.delete("/{group_id}/leave")
def leave_group(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    membership = db.query(GroupMember).filter(
        GroupMember.group_id == group_id,
        GroupMember.user_id == current_user.id
    ).first()
    if not membership:
        raise HTTPException(status_code=404, detail="You are not a member of this circle.")

    db.delete(membership)
    remaining = db.query(GroupMember).filter(GroupMember.group_id == group_id).count()
    if remaining == 0:
        group = db.query(FamilyGroup).filter(FamilyGroup.id == group_id).first()
        if group:
            db.delete(group)
    db.commit()
    return {"message": "You left the circle."}

@router.delete("/{group_id}/delete")
def delete_group(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    group = db.query(FamilyGroup).filter(FamilyGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Circle not found.")

    if group.created_by_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the circle creator can delete this circle.")

    db.delete(group)
    db.commit()
    return {"message": f"Circle '{group.name}' has been deleted."}

@router.get("/{group_id}/members")
def get_group_members(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    group = db.query(FamilyGroup).filter(FamilyGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Circle not found.")

    my_membership = db.query(GroupMember).filter(
        GroupMember.group_id == group_id,
        GroupMember.user_id == current_user.id
    ).first()
    if not my_membership:
        raise HTTPException(status_code=403, detail="You are not a member of this circle.")

    memberships = db.query(GroupMember).filter(GroupMember.group_id == group_id).all()
    members_data = []

    for m in memberships:
        u = m.user
        if not u:
            continue
        latest_loc = db.query(Location).filter(Location.user_id == u.id).order_by(desc(Location.timestamp)).first()
        is_live = bool(latest_loc and (u.is_sharing or u.is_sos_active))
        members_data.append({
            "user_id": u.id,
            "username": u.username,
            "full_name": u.full_name,
            "avatar_url": u.avatar_url,
            "role": m.role,
            "is_me": u.id == current_user.id,
            "is_sharing": u.is_sharing,
            "is_sos": bool(u.is_sos_active),
            "is_live": is_live,
            "battery_level": latest_loc.battery_level if latest_loc else None,
            "latitude": latest_loc.latitude if is_live else None,
            "longitude": latest_loc.longitude if is_live else None,
            "joined_at": m.joined_at.strftime("%b %d, %Y") if m.joined_at else None
        })

    is_admin = my_membership.role == "admin" or group.created_by_id == current_user.id
    return {
        "group_id": group.id,
        "name": group.name,
        "invite_code": group.invite_code,
        "is_admin": is_admin,
        "total_members": len(members_data),
        "members": members_data
    }

@router.delete("/{group_id}/members/{target_user_id}")
def remove_group_member(
    group_id: int,
    target_user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    group = db.query(FamilyGroup).filter(FamilyGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Circle not found.")

    my_membership = db.query(GroupMember).filter(
        GroupMember.group_id == group_id,
        GroupMember.user_id == current_user.id
    ).first()
    if not my_membership:
        raise HTTPException(status_code=403, detail="You are not a member of this circle.")

    is_admin = my_membership.role == "admin" or group.created_by_id == current_user.id

    if target_user_id != current_user.id and not is_admin:
        raise HTTPException(status_code=403, detail="Only circle admins can remove other members.")

    target_membership = db.query(GroupMember).filter(
        GroupMember.group_id == group_id,
        GroupMember.user_id == target_user_id
    ).first()
    if not target_membership:
        raise HTTPException(status_code=404, detail="User is not a member of this circle.")

    target_user = target_membership.user
    target_name = target_user.full_name if target_user else "Member"

    db.delete(target_membership)

    remaining = db.query(GroupMember).filter(GroupMember.group_id == group_id).count()
    if remaining == 0:
        db.delete(group)
    else:
        if target_user_id != current_user.id:
            db.add(Notification(
                user_id=target_user_id,
                sender_id=current_user.id,
                type="CIRCLE_REMOVED",
                title="Removed from Circle",
                message=f"You were removed from circle '{group.name}' by {current_user.full_name}."
            ))

    db.commit()
    return {"message": f"{target_name} removed from circle '{group.name}'."}