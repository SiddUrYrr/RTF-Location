from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text
)
from sqlalchemy.orm import relationship as orm_relationship
from backend.database import Base
from backend.timeutils import utcnow

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    username = Column(String(50), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(100), nullable=False)
    phone = Column(String(20), nullable=True)
    avatar_url = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    
    # Privacy & Sharing Controls
    is_sharing = Column(Boolean, default=True)
    sharing_expires_at = Column(DateTime, nullable=True)
    privacy_mode = Column(String(20), default="exact")
    is_sos_active = Column(Boolean, default=False)
    last_active = Column(DateTime, default=utcnow)
    created_at = Column(DateTime, default=utcnow)

    # Relationships
    profile = orm_relationship("Profile", back_populates="user", uselist=False, cascade="all, delete")
    locations = orm_relationship("Location", back_populates="user", cascade="all, delete")
    notifications = orm_relationship("Notification", foreign_keys="Notification.user_id", back_populates="user", cascade="all, delete")
    emergency_contacts = orm_relationship("EmergencyContact", back_populates="user", cascade="all, delete")
    group_memberships = orm_relationship("GroupMember", back_populates="user", cascade="all, delete")

class Profile(Base):
    __tablename__ = "profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    bio = Column(String(255), nullable=True)
    home_address = Column(String(255), nullable=True)
    blood_group = Column(String(10), nullable=True)
    medical_notes = Column(Text, nullable=True)
    dark_mode = Column(Boolean, default=True)

    user = orm_relationship("User", back_populates="profile")

class FriendRequest(Base):
    __tablename__ = "friend_requests"

    id = Column(Integer, primary_key=True, index=True)
    sender_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    receiver_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status = Column(String(20), default="pending")
    created_at = Column(DateTime, default=utcnow)

    sender = orm_relationship("User", foreign_keys=[sender_id])
    receiver = orm_relationship("User", foreign_keys=[receiver_id])

class Friend(Base):
    __tablename__ = "friends"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    friend_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=utcnow)

    user = orm_relationship("User", foreign_keys=[user_id])
    friend = orm_relationship("User", foreign_keys=[friend_id])

class FamilyGroup(Base):
    __tablename__ = "family_groups"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(String(255), nullable=True)
    invite_code = Column(String(12), unique=True, index=True, nullable=False)
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    created_at = Column(DateTime, default=utcnow)

    members = orm_relationship("GroupMember", back_populates="group", cascade="all, delete")

class GroupMember(Base):
    __tablename__ = "group_members"

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("family_groups.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(20), default="member")
    joined_at = Column(DateTime, default=utcnow)

    group = orm_relationship("FamilyGroup", back_populates="members")
    user = orm_relationship("User", back_populates="group_memberships")

class Location(Base):
    __tablename__ = "locations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    accuracy = Column(Float, nullable=True)
    speed = Column(Float, nullable=True)
    heading = Column(Float, nullable=True)
    battery_level = Column(Integer, nullable=True)
    is_sos = Column(Boolean, default=False)
    timestamp = Column(DateTime, default=utcnow, index=True)

    user = orm_relationship("User", back_populates="locations")

class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    sender_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    type = Column(String(50), nullable=False)
    title = Column(String(100), nullable=False)
    message = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utcnow)

    user = orm_relationship("User", foreign_keys=[user_id], back_populates="notifications")
    sender = orm_relationship("User", foreign_keys=[sender_id])

class EmergencyContact(Base):
    __tablename__ = "emergency_contacts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    phone = Column(String(20), nullable=False)
    relationship = Column(String(50), nullable=False)
    notify_in_app = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow)

    user = orm_relationship("User", back_populates="emergency_contacts")

class BlockedUser(Base):
    __tablename__ = "blocked_users"

    id = Column(Integer, primary_key=True, index=True)
    blocker_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    blocked_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=utcnow)