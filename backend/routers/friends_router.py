from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models import User, Friend, FriendRequest, Notification, GroupMember
from backend.schemas import FriendRequestCreate
from backend.auth import get_current_user
from backend.ratelimit import friend_request_limiter, rate_limit

router = APIRouter(prefix="/api/friends", tags=["Friends"])

@router.get("/")
def list_friends(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    friendships = db.query(Friend).filter(Friend.user_id == current_user.id).all()
    results = []
    for f in friendships:
        friend_user = db.query(User).filter(User.id == f.friend_id).first()
        if friend_user:
            results.append({
                "id": f.id,
                "friend": {
                    "id": friend_user.id,
                    "username": friend_user.username,
                    "full_name": friend_user.full_name,
                    "is_sharing": friend_user.is_sharing,
                    "is_sos_active": friend_user.is_sos_active
                }
            })
    return results

@router.post("/request", dependencies=[Depends(rate_limit(friend_request_limiter, "friend-request"))])
def send_friend_request(
    payload: FriendRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    ident = payload.username_or_email.strip().lower()
    if not ident:
        raise HTTPException(status_code=400, detail="Please enter a username or email.")

    if ident == current_user.username.lower() or ident == current_user.email.lower():
        raise HTTPException(status_code=400, detail="You cannot send a friend request to yourself.")

    target = db.query(User).filter(
        (User.username == ident) |
        (User.email == ident)
    ).first()

    if not target or target.id == current_user.id:
        raise HTTPException(status_code=404, detail=f"No user found with username or email '{payload.username_or_email}'. Please check spelling.")

    if db.query(Friend).filter(Friend.user_id == current_user.id, Friend.friend_id == target.id).first():
        raise HTTPException(status_code=400, detail=f"{target.full_name} is already in your family list.")

    # Check if a pending request was already sent to target
    existing_freq = db.query(FriendRequest).filter(
        FriendRequest.sender_id == current_user.id,
        FriendRequest.receiver_id == target.id,
        FriendRequest.status == "pending"
    ).first()
    if existing_freq:
        raise HTTPException(status_code=400, detail=f"A friend request to {target.full_name} is already pending.")

    # Check if target already sent a request to current_user -> auto accept!
    reverse_freq = db.query(FriendRequest).filter(
        FriendRequest.sender_id == target.id,
        FriendRequest.receiver_id == current_user.id,
        FriendRequest.status == "pending"
    ).first()
    if reverse_freq:
        reverse_freq.status = "accepted"
        if not db.query(Friend).filter(Friend.user_id == current_user.id, Friend.friend_id == target.id).first():
            db.add(Friend(user_id=current_user.id, friend_id=target.id))
        if not db.query(Friend).filter(Friend.user_id == target.id, Friend.friend_id == current_user.id).first():
            db.add(Friend(user_id=target.id, friend_id=current_user.id))
        db.add(Notification(
            user_id=target.id,
            sender_id=current_user.id,
            type="FRIEND_ACCEPTED",
            title="Friend Connected",
            message=f"{current_user.full_name} and you are now connected!"
        ))
        db.commit()
        return {"message": f"{target.full_name} had already sent you a request! You are now connected."}

    freq = FriendRequest(sender_id=current_user.id, receiver_id=target.id, status="pending")
    db.add(freq)
    db.add(Notification(
        user_id=target.id,
        sender_id=current_user.id,
        type="FRIEND_REQUEST",
        title="Friend Request",
        message=f"{current_user.full_name} sent you a friend request."
    ))
    db.commit()
    return {"message": f"Friend request sent to {target.full_name} (@{target.username}) successfully!"}

@router.get("/requests")
def get_incoming_requests(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    requests = db.query(FriendRequest).filter(
        FriendRequest.receiver_id == current_user.id,
        FriendRequest.status == "pending"
    ).all()
    return [{
        "id": r.id,
        "sender": {
            "id": r.sender.id,
            "username": r.sender.username,
            "full_name": r.sender.full_name
        }
    } for r in requests if r.sender]

@router.post("/requests/{req_id}/respond")
def respond_request(
    req_id: int,
    action: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    freq = db.query(FriendRequest).filter(
        FriendRequest.id == req_id,
        FriendRequest.receiver_id == current_user.id,
        FriendRequest.status == "pending"
    ).first()
    if not freq:
        raise HTTPException(status_code=404, detail="Request not found.")

    if action == "accept":
        freq.status = "accepted"
        if not db.query(Friend).filter(Friend.user_id == current_user.id, Friend.friend_id == freq.sender_id).first():
            db.add(Friend(user_id=current_user.id, friend_id=freq.sender_id))
        if not db.query(Friend).filter(Friend.user_id == freq.sender_id, Friend.friend_id == current_user.id).first():
            db.add(Friend(user_id=freq.sender_id, friend_id=current_user.id))

        db.add(Notification(
            user_id=freq.sender_id,
            sender_id=current_user.id,
            type="FRIEND_ACCEPTED",
            title="Friend Request Accepted",
            message=f"{current_user.full_name} accepted your friend request!"
        ))
    else:
        freq.status = "rejected"

    db.commit()
    return {"message": f"Request {action}ed successfully."}

@router.delete("/{friend_user_id}")
def remove_friend(
    friend_user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    target = db.query(User).filter(User.id == friend_user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")

    f1 = db.query(Friend).filter(Friend.user_id == current_user.id, Friend.friend_id == friend_user_id).first()
    f2 = db.query(Friend).filter(Friend.user_id == friend_user_id, Friend.friend_id == current_user.id).first()

    # Find any shared circles where current_user is admin
    my_admin_groups = [
        gm.group_id for gm in db.query(GroupMember).filter(
            GroupMember.user_id == current_user.id,
            GroupMember.role == "admin"
        ).all()
    ]
    target_memberships_in_my_groups = db.query(GroupMember).filter(
        GroupMember.user_id == friend_user_id,
        GroupMember.group_id.in_(my_admin_groups)
    ).all() if my_admin_groups else []

    has_friendship = bool(f1 or f2)
    has_admin_group = bool(target_memberships_in_my_groups)

    # Check if they share any groups at all
    my_all_groups = [
        gm.group_id for gm in db.query(GroupMember).filter(
            GroupMember.user_id == current_user.id
        ).all()
    ]
    shared_group_count = db.query(GroupMember).filter(
        GroupMember.user_id == friend_user_id,
        GroupMember.group_id.in_(my_all_groups)
    ).count() if my_all_groups else 0

    if not has_friendship and not has_admin_group and shared_group_count == 0:
        raise HTTPException(status_code=404, detail="Member not found in your family list.")

    # 1. Delete friendships
    if f1:
        db.delete(f1)
    if f2:
        db.delete(f2)

    # 2. Delete friend requests
    db.query(FriendRequest).filter(
        ((FriendRequest.sender_id == current_user.id) & (FriendRequest.receiver_id == friend_user_id)) |
        ((FriendRequest.sender_id == friend_user_id) & (FriendRequest.receiver_id == current_user.id))
    ).delete(synchronize_session=False)

    # 3. Remove from admin circles
    for gm in target_memberships_in_my_groups:
        db.delete(gm)

    db.commit()

    if not has_friendship and not has_admin_group and shared_group_count > 0:
        return {
            "message": f"{target.full_name} is in a circle where you are not admin. You can leave that circle from the Circles tab to disconnect."
        }

    return {"message": f"{target.full_name} removed from family list."}