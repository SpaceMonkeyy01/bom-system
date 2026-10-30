from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth_routes import router as auth_router
from app.api.routes import router
from app.api.inventory_routes import router as inventory_router
from app.api.report_routes import router as report_router
from app.api.sync_routes import router as sync_router
from app.api.template_routes import router as template_router
from app.config import settings
from app.db import SessionLocal
from app.services.auth import bootstrap_admin


@asynccontextmanager
async def lifespan(_: FastAPI):
    db = SessionLocal()
    try:
        bootstrap_admin(db)
    finally:
        db.close()
    yield


app = FastAPI(title="BOM System API", version="0.2.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(auth_router, prefix="/api", tags=["auth"])
app.include_router(template_router, prefix="/api", tags=["templates"])  # before the generic /templates/{id}
app.include_router(inventory_router, prefix="/api", tags=["inventory"])  # /materials/review before /materials/{id}
app.include_router(sync_router, prefix="/api", tags=["sync"])
app.include_router(report_router, prefix="/api", tags=["reports"])
app.include_router(router, prefix="/api")


@app.get("/health")
def health():
    return {"ok": True, "env": settings.environment}
