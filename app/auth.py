import os
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Dict, Optional
import json

# Simple file-based user storage (can upgrade to DB later)
USERS_FILE = "data/users.json"
SESSIONS_FILE = "data/sessions.json"

def ensure_data_dir():
    os.makedirs("data", exist_ok=True)
    if not os.path.exists(USERS_FILE):
        with open(USERS_FILE, "w") as f:
            json.dump({}, f)
    if not os.path.exists(SESSIONS_FILE):
        with open(SESSIONS_FILE, "w") as f:
            json.dump({}, f)

def hash_password(password: str) -> str:
    """Hash password with salt."""
    salt = "contentblast_salt_2024"
    return hashlib.sha256((password + salt).encode()).hexdigest()

def load_users() -> Dict:
    ensure_data_dir()
    with open(USERS_FILE, "r") as f:
        return json.load(f)

def save_users(users: Dict):
    ensure_data_dir()
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)

def load_sessions() -> Dict:
    ensure_data_dir()
    with open(SESSIONS_FILE, "r") as f:
        return json.load(f)

def save_sessions(sessions: Dict):
    ensure_data_dir()
    with open(SESSIONS_FILE, "w") as f:
        json.dump(sessions, f, indent=2)

class AuthSystem:
    """
    User authentication system for ContentBlast.
    """

    # Free tier limits
    FREE_REPURPOSES = 5
    STARTER_REPURPOSES = 50
    PRO_REPURPOSES = 200

    @staticmethod
    def register(email: str, password: str, name: str = "") -> Dict:
        """Register a new user."""
        email = email.lower().strip()

        if not email or "@" not in email:
            return {"success": False, "error": "Invalid email address"}

        if len(password) < 6:
            return {"success": False, "error": "Password must be at least 6 characters"}

        users = load_users()

        if email in users:
            return {"success": False, "error": "Email already registered"}

        users[email] = {
            "email": email,
            "password": hash_password(password),
            "name": name or email.split("@")[0],
            "plan": "free",
            "repurposes_used": 0,
            "repurposes_limit": AuthSystem.FREE_REPURPOSES,
            "created_at": datetime.now().isoformat(),
            "last_login": None
        }

        save_users(users)

        return {"success": True, "message": "Account created successfully"}

    @staticmethod
    def login(email: str, password: str) -> Dict:
        """Login user and create session."""
        email = email.lower().strip()
        users = load_users()

        if email not in users:
            return {"success": False, "error": "Invalid email or password"}

        if users[email]["password"] != hash_password(password):
            return {"success": False, "error": "Invalid email or password"}

        # Update last login
        users[email]["last_login"] = datetime.now().isoformat()
        save_users(users)

        # Create session
        session_token = secrets.token_urlsafe(32)
        sessions = load_sessions()
        sessions[session_token] = {
            "email": email,
            "created_at": datetime.now().isoformat(),
            "expires_at": (datetime.now() + timedelta(days=7)).isoformat()
        }
        save_sessions(sessions)

        return {
            "success": True,
            "session_token": session_token,
            "user": {
                "email": email,
                "name": users[email]["name"],
                "plan": users[email]["plan"],
                "repurposes_used": users[email]["repurposes_used"],
                "repurposes_limit": users[email]["repurposes_limit"]
            }
        }

    @staticmethod
    def get_user_from_session(session_token: str) -> Optional[Dict]:
        """Get user from session token."""
        if not session_token:
            return None

        sessions = load_sessions()

        if session_token not in sessions:
            return None

        session = sessions[session_token]

        # Check expiration
        if datetime.fromisoformat(session["expires_at"]) < datetime.now():
            del sessions[session_token]
            save_sessions(sessions)
            return None

        users = load_users()
        email = session["email"]

        if email not in users:
            return None

        user = users[email]
        return {
            "email": email,
            "name": user["name"],
            "plan": user["plan"],
            "repurposes_used": user["repurposes_used"],
            "repurposes_limit": user["repurposes_limit"],
            "repurposes_remaining": user["repurposes_limit"] - user["repurposes_used"] if user["repurposes_limit"] > 0 else 999
        }

    @staticmethod
    def use_repurpose(email: str) -> Dict:
        """Use one repurpose credit."""
        users = load_users()

        if email not in users:
            return {"success": False, "error": "User not found"}

        user = users[email]

        # Check limit (-1 means unlimited)
        if user["repurposes_limit"] > 0 and user["repurposes_used"] >= user["repurposes_limit"]:
            return {"success": False, "error": "Repurpose limit reached. Please upgrade!"}

        user["repurposes_used"] += 1
        save_users(users)

        return {
            "success": True,
            "repurposes_used": user["repurposes_used"],
            "repurposes_remaining": user["repurposes_limit"] - user["repurposes_used"] if user["repurposes_limit"] > 0 else 999
        }

    @staticmethod
    def logout(session_token: str) -> Dict:
        """Logout user by removing session."""
        sessions = load_sessions()

        if session_token in sessions:
            del sessions[session_token]
            save_sessions(sessions)

        return {"success": True}

    @staticmethod
    def upgrade_plan(email: str, plan: str) -> Dict:
        """Upgrade user plan."""
        users = load_users()

        if email not in users:
            return {"success": False, "error": "User not found"}

        limits = {
            "free": AuthSystem.FREE_REPURPOSES,
            "starter": AuthSystem.STARTER_REPURPOSES,
            "pro": AuthSystem.PRO_REPURPOSES,
            "unlimited": -1
        }

        if plan not in limits:
            return {"success": False, "error": "Invalid plan"}

        users[email]["plan"] = plan
        users[email]["repurposes_limit"] = limits[plan]
        users[email]["repurposes_used"] = 0  # Reset on upgrade
        save_users(users)

        return {"success": True, "plan": plan}
