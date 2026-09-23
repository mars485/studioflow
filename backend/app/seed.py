"""Idempotent local setup; creates no sample clients or deals."""
import asyncio
from uuid import UUID

from app.core.config import settings
from app.core.database import SessionLocal, engine
from app.models import Pipeline, PipelineStage, User, Workspace, WorkspaceMember

WORKSPACE_ID = UUID("00000000-0000-0000-0000-000000000002")
PIPELINE_ID = UUID("00000000-0000-0000-0000-000000000003")
MEMBER_ID = UUID("00000000-0000-0000-0000-000000000004")


async def seed():
    if not settings.dev_auth_enabled:
        return
    async with SessionLocal() as db:
        if await db.get(Workspace, WORKSPACE_ID):
            return
        user_id = UUID(settings.dev_user_id)
        if not await db.get(User, user_id):
            db.add(User(id=user_id, email="local@studioflow.invalid", password_hash="!disabled",
                        first_name="Local", is_active=True))
        db.add(Workspace(id=WORKSPACE_ID, name="StudioFlow", slug="local"))
        await db.flush()
        db.add(WorkspaceMember(id=MEMBER_ID, workspace_id=WORKSPACE_ID, user_id=user_id, role="OWNER"))
        db.add(Pipeline(id=PIPELINE_ID, workspace_id=WORKSPACE_ID, name="Продажи", is_default=True))
        await db.flush()
        for position, name in enumerate(("Новый лид", "Контакт", "КП отправлено", "Переговоры")):
            db.add(PipelineStage(workspace_id=WORKSPACE_ID, pipeline_id=PIPELINE_ID,
                                 name=name, position=position))
        await db.commit()


async def main():
    try:
        await seed()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
