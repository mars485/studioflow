from fastapi import FastAPI
from app.api.v1.health import router as health_router
from app.api.v1.crm import router as crm_router
from app.api.v1.projects import router as projects_router
from app.api.v1.finance import router as finance_router
from app.api.v1.attachments import router as attachments_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.project_work import router as project_work_router
from app.api.v1.project_templates import router as project_templates_router
from app.api.v1.integrations import router as integrations_router
from app.api.v1.task_time import router as task_time_router
from app.api.v1.task_recurrence import router as task_recurrence_router
from app.api.v1.webhooks import router as webhooks_router
from app.api.v1.analytics import router as analytics_router
from app.api.v1.exports import router as exports_router
from app.api.v1.search import router as search_router
from app.api.v1.audit import router as audit_router
from app.api.v1.duplicates import router as duplicates_router
from app.api.v1.auth import router as auth_router
from app.api.v1.workspaces import router as workspace_router
from starlette.responses import JSONResponse
from app.core.config import settings

app = FastAPI(title=settings.app_name, version="0.1.0")
app.include_router(health_router, prefix="/api/v1")
app.include_router(crm_router, prefix="/api/v1")
app.include_router(projects_router, prefix="/api/v1")
app.include_router(finance_router, prefix="/api/v1")
app.include_router(attachments_router, prefix="/api/v1")
app.include_router(notifications_router, prefix="/api/v1")
app.include_router(project_work_router, prefix="/api/v1")
app.include_router(project_templates_router, prefix="/api/v1")
app.include_router(integrations_router, prefix="/api/v1")
app.include_router(task_time_router, prefix="/api/v1")
app.include_router(task_recurrence_router, prefix="/api/v1")
app.include_router(webhooks_router, prefix="/api/v1")
app.include_router(analytics_router, prefix="/api/v1")
app.include_router(exports_router, prefix="/api/v1")
app.include_router(search_router, prefix="/api/v1")
app.include_router(audit_router, prefix="/api/v1")
app.include_router(duplicates_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(workspace_router, prefix="/api/v1")


@app.middleware("http")
async def protect_api(request, call_next):
    if request.url.path.startswith("/api/"):
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            if (request.headers.get("X-StudioFlow-Request") != "1"
                    or request.headers.get("sec-fetch-site") == "cross-site"
                    or (origin and origin not in settings.allowed_origins)):
                return JSONResponse({"detail": "Недопустимый источник запроса"}, status_code=403)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response
    return await call_next(request)

@app.get("/", include_in_schema=False)
async def root():
    return {"message": "StudioFlow API", "docs": "/docs"}

