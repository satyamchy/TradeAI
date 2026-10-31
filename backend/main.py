"""Compatibility launcher for the single FastAPI application."""

from app.application import app
from app.shared.config import settings

__all__ = ["app"]


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.backend_host,
        port=settings.backend_port,
        reload=settings.app_debug,
    )
