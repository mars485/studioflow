from fastapi import FastAPI
from app.api.v1.health import router as health_router
from app.api.v1.crm import router as crm_router
from app.api.v1.auth import router as auth_router
from app.api.v1.workspaces import router as workspace_router
from starlette.responses import JSONResponse
from app.core.config import settings

app = FastAPI(title=settings.app_name, version="0.1.0")
app.include_router(health_router, prefix="/api/v1")
app.include_router(crm_router, prefix="/api/v1")
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

