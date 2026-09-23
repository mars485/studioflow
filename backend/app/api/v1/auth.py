from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.api.dependencies import current_user
from app.core.database import get_db
from app.core.security import COOKIE, hash_password, issue_session, revoke_session, throttle, verify_password
from app.models import User

router = APIRouter(prefix="/auth", tags=["Authentication"])


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: Annotated[str, Field(min_length=12, max_length=128)]

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value):
        return value.lower()


class Registration(Credentials):
    first_name: Annotated[str, StringConstraints(min_length=1, max_length=100, strip_whitespace=True)]

    @field_validator("first_name")
    @classmethod
    def clean_name(cls, value):
        if not value.strip():
            raise ValueError("Укажите имя")
        return value.strip()


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    email: str
    first_name: str


@router.post("/register", response_model=UserOut, status_code=201)
async def register(data: Registration, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    await throttle(db, request, data.email)
    user = User(email=data.email, first_name=data.first_name,
                password_hash=await run_in_threadpool(hash_password, data.password))
    db.add(user)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "Не удалось зарегистрировать этот email. Попробуйте войти.")
    await issue_session(db, user.id, request, response)
    return user


@router.post("/login", response_model=UserOut)
async def login(data: Credentials, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    await throttle(db, request, data.email)
    user = await db.scalar(select(User).where(User.email == data.email))
    valid = await run_in_threadpool(verify_password, data.password, user.password_hash if user else None)
    if not valid or not user or not user.is_active:
        raise HTTPException(401, "Неверный email или пароль")
    await issue_session(db, user.id, request, response)
    return user


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(current_user)):
    return user


@router.post("/logout", status_code=204)
async def logout(request: Request, db: AsyncSession = Depends(get_db)):
    await revoke_session(db, request.cookies.get(COOKIE))
    await db.commit()
    response = Response(status_code=204)
    response.delete_cookie(COOKIE, path="/api", httponly=True, samesite="lax")
    return response
