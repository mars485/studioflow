from fastapi import FastAPI
from app.api.v1.health import router as health_router
from app.api.v1.crm import router as crm_router
from app.core.config import settings

app = FastAPI(title=settings.app_name, version="0.1.0")
app.include_router(health_router, prefix="/api/v1")
app.include_router(crm_router, prefix="/api/v1")

@app.get("/", include_in_schema=False)
async def root():
    return {"message": "StudioFlow API", "docs": "/docs"}

