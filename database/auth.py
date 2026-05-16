"""
project_QLE/database/auth.py
─────────────────────────────
Access control for Project_QLE.

Design
──────
  - Owner holds the MASTER key (set once on first run).
  - Users must register and get an ACCESS KEY from the owner.
  - All keys are SHA-256 hashed before storage.
  - Admin dashboard (admin_dashboard.py) lets the owner manage users.

Tables used: users (in the same SQLite DB as projects/wells)
"""
from __future__ import annotations
import hashlib
import os
import secrets
import string
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.orm import Session

# Re-use the same engine/Base from db.py
from project_QLE.database.db import Base, ENGINE, get_session


# ── User model ───────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id         = Column(Integer, primary_key=True)
    username   = Column(String(100), unique=True, nullable=False)
    key_hash   = Column(String(64), nullable=False)    # SHA-256 hex
    role       = Column(String(20), default="user")    # 'owner' | 'user'
    is_active  = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_seen  = Column(DateTime)
    notes      = Column(Text, default="")

    def __repr__(self):
        return f"<User {self.username} role={self.role} active={self.is_active}>"


# ── Key utilities ────────────────────────────────────────────

def _hash(key: str) -> str:
    """Return SHA-256 hex digest of a key."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _generate_key(length: int = 20) -> str:
    """Generate a random alphanumeric access key."""
    alphabet = string.ascii_letters + string.digits
    return "QLE-" + "".join(secrets.choice(alphabet) for _ in range(length))


# ── Bootstrap ────────────────────────────────────────────────

def init_auth():
    """Create the users table and add the owner account if it doesn't exist."""
    Base.metadata.create_all(ENGINE)

    session = get_session()
    try:
        owner = session.query(User).filter_by(role="owner").first()
        if owner is None:
            # First run: create owner with a key from env or a generated one
            master_key = os.environ.get("QLE_MASTER_KEY") or _generate_key(24)
            owner = User(
                username  = "owner",
                key_hash  = _hash(master_key),
                role      = "owner",
                is_active = True,
            )
            session.add(owner)
            session.commit()
            # Write to a local file so the owner can read it on first run
            key_file = os.path.expanduser("~/.project_qle/owner_key.txt")
            os.makedirs(os.path.dirname(key_file), exist_ok=True)
            with open(key_file, "w") as f:
                f.write(f"PROJECT_QLE OWNER KEY\n{'='*35}\n{master_key}\n")
                f.write("Keep this file secret. Give user keys from the admin dashboard.\n")
            print(f"\n{'='*50}")
            print(f"  FIRST RUN — Owner key saved to: {key_file}")
            print(f"  Master key: {master_key}")
            print(f"{'='*50}\n")
    finally:
        session.close()


# ── Authentication ───────────────────────────────────────────

def authenticate(key: str) -> Optional[User]:
    """
    Verify an access key. Returns the User if valid and active, else None.

    Parameters
    ----------
    key : str
        Raw access key entered by the user.
    """
    if not key or not key.strip():
        return None
    key_hash = _hash(key.strip())
    session = get_session()
    try:
        user = session.query(User).filter_by(
            key_hash=key_hash, is_active=True
        ).first()
        if user:
            # Update last_seen
            user.last_seen = datetime.utcnow()
            session.commit()
        return user
    finally:
        session.close()


def is_owner(key: str) -> bool:
    """Return True if the key belongs to the owner."""
    user = authenticate(key)
    return user is not None and user.role == "owner"


# ── User management (called from admin dashboard) ────────────

def create_user(username: str, notes: str = "") -> str:
    """
    Create a new user and return their generated access key.
    The caller must securely deliver this key to the user.
    """
    key = _generate_key(20)
    session = get_session()
    try:
        user = User(
            username  = username,
            key_hash  = _hash(key),
            role      = "user",
            is_active = True,
            notes     = notes,
        )
        session.add(user)
        session.commit()
        return key
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def deactivate_user(username: str) -> bool:
    """Deactivate (ban) a user without deleting their data."""
    session = get_session()
    try:
        user = session.query(User).filter_by(username=username).first()
        if user and user.role != "owner":
            user.is_active = False
            session.commit()
            return True
        return False
    finally:
        session.close()


def reactivate_user(username: str) -> bool:
    """Re-enable a previously deactivated user."""
    session = get_session()
    try:
        user = session.query(User).filter_by(username=username).first()
        if user:
            user.is_active = True
            session.commit()
            return True
        return False
    finally:
        session.close()


def regenerate_key(username: str) -> Optional[str]:
    """Generate a new key for an existing user (old key immediately invalidated)."""
    session = get_session()
    try:
        user = session.query(User).filter_by(username=username).first()
        if user and user.role != "owner":
            new_key = _generate_key(20)
            user.key_hash = _hash(new_key)
            session.commit()
            return new_key
        return None
    finally:
        session.close()


def list_users() -> list[dict]:
    """Return all users as a list of dicts (no key hashes)."""
    session = get_session()
    try:
        users = session.query(User).all()
        return [
            {
                "username"  : u.username,
                "role"      : u.role,
                "active"    : u.is_active,
                "created"   : u.created_at.strftime("%Y-%m-%d") if u.created_at else "",
                "last_seen" : u.last_seen.strftime("%Y-%m-%d %H:%M") if u.last_seen else "never",
                "notes"     : u.notes,
            }
            for u in users
        ]
    finally:
        session.close()


def delete_user(username: str) -> bool:
    """Permanently delete a non-owner user."""
    session = get_session()
    try:
        user = session.query(User).filter_by(username=username).first()
        if user and user.role != "owner":
            session.delete(user)
            session.commit()
            return True
        return False
    finally:
        session.close()