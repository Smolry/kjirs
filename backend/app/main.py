import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.cache import DataCache
from app.config import get_settings

settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    description="Wind forecast monitoring and accuracy evaluation for day-ahead purchase decisions.",
    version="1.0.0",
)
app.state.settings = settings
app.state.cache = DataCache(settings.cache_mode, settings.cache_dir, settings.cache_ttl_seconds)
app.state.data_lock = asyncio.Lock()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)
app.include_router(router)


@app.get("/")
async def root():
    return {"name": settings.app_name, "docs": "/docs", "health": "/api/health"}
