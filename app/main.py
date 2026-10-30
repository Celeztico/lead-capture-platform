from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.v1 import public as public_router
from app.api.v1 import widgets as widgets_router
from app.api.v1.health import router as health_router
from app.core.config import get_settings
from app.core.database import close_db, init_db
from app.middleware.cache import CacheControlMiddleware
from app.middleware.cors import PathScopedCORSMiddleware
from app.middleware.logging import CorrelationIdMiddleware

settings = get_settings()

WIDGET_ASSETS_DIR = Path(__file__).resolve().parent / "static" / "widget" / "v1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield
    await close_db()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )

    app.add_middleware(CorrelationIdMiddleware)

    # Cache headers for versioned widget assets (paths are versioned, so a
    # moderate lifetime with revalidation is safe).
    app.add_middleware(
        CacheControlMiddleware,
        paths=("/widget",),
        cache_control="public, max-age=3600, stale-while-revalidate=86400",
    )

    # Management API CORS (dashboard and other first-party web apps)
    app.add_middleware(
        PathScopedCORSMiddleware,
        paths=("/api",),
        allow_origins=settings.allowed_origins_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    # CORS for public widget endpoints only (config + script delivery)
    widget_origins = settings.allowed_widget_origins_list
    app.add_middleware(
        PathScopedCORSMiddleware,
        paths=("/public", "/widget"),
        allow_origins=widget_origins if widget_origins else ["*"],
        allow_credentials=False,
        allow_methods=["GET", "OPTIONS"],
        allow_headers=["Origin", "Accept", "Content-Type", "If-None-Match"],
        expose_headers=["ETag", "Cache-Control"],
    )

    # Serve versioned widget JavaScript assets
    app.mount(
        "/widget/v1",
        StaticFiles(directory=str(WIDGET_ASSETS_DIR)),
        name="widget-assets",
    )

    app.include_router(health_router, prefix="/api/v1")
    app.include_router(public_router.router)
    app.include_router(widgets_router.router)

    return app


app = create_app()
