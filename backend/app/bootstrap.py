"""Claim the disabled local seed account without changing its ID or CRM data."""
import asyncio
from getpass import getpass

from pydantic import TypeAdapter, EmailStr
from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import User


async def activate(email: str, name: str, password: str):
    email = str(TypeAdapter(EmailStr).validate_python(email)).lower()
    if not 12 <= len(password) <= 128 or not 1 <= len(name.strip()) <= 100:
        raise ValueError("Имя: 1–100 символов, пароль: 12–128 символов")
    async with SessionLocal() as db:
        user = await db.scalar(select(User).where(User.id == settings.dev_user_id).with_for_update())
        if not user or user.password_hash != "!disabled" or user.email != "local@studioflow.invalid":
            raise ValueError("Не найден неактивированный локальный аккаунт. Используйте регистрацию или вход.")
        if await db.scalar(select(User.id).where(User.email == email, User.id != user.id)):
            raise ValueError("Email уже занят другим аккаунтом")
        user.email, user.first_name = email, name.strip()
        user.password_hash, user.is_active = hash_password(password), True
        await db.commit()


def main():
    email = input("Email владельца: ").strip()
    name = input("Имя: ").strip()
    password = getpass("Пароль (12–128 символов): ")
    if password != getpass("Повторите пароль: "):
        raise SystemExit("Пароли не совпадают")
    try:
        asyncio.run(activate(email, name, password))
    except ValueError as error:
        raise SystemExit(str(error))
    print("Аккаунт активирован. Войдите через форму. Сделки и рабочее пространство сохранены.")


if __name__ == "__main__":
    main()
