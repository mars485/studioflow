import os
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.database import get_db
from app.core.security import hash_password
from app.main import app
from app.models import Client, Pipeline, PipelineStage, User, Workspace, WorkspaceMember


@pytest_asyncio.fixture
async def crm(monkeypatch):
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to a migrated disposable PostgreSQL database")
    engine = create_async_engine(url, poolclass=NullPool)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        async with AsyncSession(bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint") as db:
            user = User(id=uuid4(), email=f"{uuid4()}@example.com", password_hash=hash_password("test-password-123"), first_name="Tester")
            spaces = [Workspace(id=uuid4(), name=f"Space {i}", slug=str(uuid4())) for i in range(2)]
            db.add_all([user, *spaces])
            await db.flush()
            db.add(WorkspaceMember(workspace_id=spaces[0].id, user_id=user.id))
            clients = [Client(id=uuid4(), workspace_id=w.id, name=f"Client {i}") for i, w in enumerate(spaces)]
            pipelines = [Pipeline(id=uuid4(), workspace_id=w.id, name="Sales", is_default=True) for w in spaces]
            db.add_all([*clients, *pipelines])
            await db.flush()
            stages = [PipelineStage(id=uuid4(), workspace_id=p.workspace_id, pipeline_id=p.id,
                                    name=f"Stage {i}", position=i) for i, p in enumerate(pipelines)]
            next_stage = PipelineStage(id=uuid4(), workspace_id=spaces[0].id, pipeline_id=pipelines[0].id, name="Next", position=2)
            db.add_all([*stages, next_stage])
            await db.commit()
            monkeypatch.setattr(settings, "dev_auth_enabled", True)
            monkeypatch.setattr(settings, "dev_user_id", str(user.id))

            async def override_db():
                yield db

            app.dependency_overrides[get_db] = override_db
            try:
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers={"X-StudioFlow-Request": "1"}) as http:
                    response = await http.post("/api/v1/auth/login", json={"email": user.email, "password": "test-password-123"})
                    assert response.status_code == 200, response.text
                    yield {"http": http, "db": db, "spaces": spaces, "clients": clients,
                           "pipelines": pipelines, "stages": stages, "next": next_stage, "user": user,
                           "base": f"/api/v1/workspaces/{spaces[0].id}",
                           "payload": {"title": "Website", "client_id": str(clients[0].id),
                                       "pipeline_id": str(pipelines[0].id), "stage_id": str(stages[0].id),
                                       "amount": "65000.25", "contact_name": "Мария", "source": "Сайт"}}
            finally:
                app.dependency_overrides.clear()
        await transaction.rollback()
    await engine.dispose()
