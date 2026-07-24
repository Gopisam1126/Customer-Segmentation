"""
auth.py
Minimal hardcoded authentication for demo purposes only.

This is NOT production-grade auth. There is a single hardcoded account;
the password is stored as a SHA-256 hash (not plaintext) purely so the
demo shows a hashing step rather than comparing raw strings. Session
state is Flask's signed cookie session, which is fine for a local demo
but should be swapped for a real user store + proper session backend
before shipping.
"""

import hashlib

# ── Hardcoded demo account ───────────────────────────────────────────────────
# Username: admin   Password: mall2026
DEMO_USERNAME = "admin"
_DEMO_PASSWORD_HASH = hashlib.sha256("mall2026".encode("utf-8")).hexdigest()


def hash_password(raw_password: str) -> str:
    """SHA-256 hex digest of a plaintext password."""
    return hashlib.sha256(raw_password.encode("utf-8")).hexdigest()


def verify_credentials(username: str, password: str) -> bool:
    """Check a username/password pair against the hardcoded demo account."""
    if not username or not password:
        return False
    return username.strip() == DEMO_USERNAME and hash_password(password) == _DEMO_PASSWORD_HASH
