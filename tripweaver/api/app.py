"""FastAPI application factory."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from tripweaver.api.routes import router

WEB_DIR = Path(__file__).resolve().parents[1] / "web"


def create_app() -> FastAPI:
    application = FastAPI(
        title="TripMate AI",
        description=(
            "LangGraph Multi-Agent Travel Planner with Supervisor, Guardrails, "
            "Human-in-the-Loop, and FastAPI Frontend"
        ),
        version="2.0.0",
    )
    application.mount(
        "/static",
        StaticFiles(directory=str(WEB_DIR / "static")),
        name="static",
    )
    application.include_router(router)
    return application


app = create_app()
