import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request, Response
from sqlalchemy import case, delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.entities import AuthSession, AuthThrottle

COOKIE = "studioflow_session"


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    # OWASP equivalent scrypt profile: N=2^14, r=8, p=5 (16 MiB).
    value = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=5, maxmem=64 * 1024 * 1024).hex()
    return f"scrypt${salt}${value}"


def verify_password(password: str, encoded: str | None) -> bool:
    if not encoded or not encoded.startswith("scrypt$"):
        hash_password(password, "00" * 16)
        return False
    try:
        _, salt, _ = encoded.split("$")
        return hmac.compare_digest(hash_password(password, salt), encoded)
    except (ValueError, TypeError):
        return False


async def revoke_session(db: AsyncSession, token: str | None):
    if token:
        await db.execute(delete(AuthSession).where(AuthSession.token_hash == token_digest(token)))


async def issue_session(db: AsyncSession, user_id, request: Request, response: Response):
    await revoke_session(db, request.cookies.get(COOKIE))
    now = datetime.now(timezone.utc)
    await db.execute(delete(AuthSession).where(AuthSession.expires_at <= now))
    token = secrets.token_urlsafe(32)
    db.add(AuthSession(token_hash=token_digest(token), user_id=user_id,
                       expires_at=now + timedelta(hours=settings.session_hours)))
    await db.commit()
    response.set_cookie(COOKIE, token, max_age=settings.session_hours * 3600,
                        httponly=True, secure=settings.session_cookie_secure, samesite="lax", path="/api")
    response.headers["Cache-Control"] = "no-store"


async def throttle(db: AsyncSession, request: Request, email: str):
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=15)
    await db.execute(delete(AuthThrottle).where(AuthThrottle.window_start < now - timedelta(days=1)))
    # Database counters work across API workers. Ignore spoofable forwarded headers.
    buckets = [("email:" + email, 20), ("ip:" + (request.client.host if request.client else "unknown"), 100)]
    blocked = False
    for key, limit in buckets:
        statement = insert(AuthThrottle).values(key=token_digest(key), attempts=1, window_start=now)
        statement = statement.on_conflict_do_update(index_elements=[AuthThrottle.key], set_={
            "attempts": case((AuthThrottle.window_start < cutoff, 1), else_=AuthThrottle.attempts + 1),
            "window_start": case((AuthThrottle.window_start < cutoff, now), else_=AuthThrottle.window_start),
        }).returning(AuthThrottle.attempts)
        blocked |= (await db.scalar(statement)) > limit
    await db.commit()
    if blocked:
        raise HTTPException(429, "Слишком много попыток. Повторите через 15 минут.", headers={"Retry-After": "900"})
