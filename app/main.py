from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1 import public as public_router
from app.api.v1 import widgets as widgets_router
from app.api.v1.health import router as health_router
from app.core.config import get_settings
from app.core.database import close_db, init_db
from app.middleware.logging import CorrelationIdMiddleware

settings = get_settings()


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

    # CORS for public widget endpoints only (config + script delivery)
    widget_origins = settings.allowed_widget_origins_list
    allow_widget_star = "*" in widget_origins

    app.add_middleware(
        CORSMiddleware,
        allow_origins=widget_origins if widget_origins else ["*"],
        allow_credentials=False,
        allow_methods=["GET", "OPTIONS"],
        allow_headers=["Origin", "Accept", "Content-Type", "If-None-Match"],
        expose_headers=["ETag", "Cache-Control"],
    )

    # Serve versioned widget JavaScript assets
    app.mount(
        "/widget/v1",
        StaticFiles(directory="app/static/widget/v1"),
        name="widget-assets",
    )

    app.include_router(health_router, prefix="/api/v1")
    app.include_router(public_router.router)
    app.include_router(widgets_router.router)

    return app


app = create_app()