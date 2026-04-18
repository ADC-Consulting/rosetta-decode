"""FastAPI application entrypoint for the backend service."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.backend.api.routes import jobs, migrate
from src.backend.core.config import settings
from src.backend.core.logging import configure_logging

configure_logging()

app = FastAPI(
    title="Rosetta Decode API",
    description="SAS-to-Python migration service",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
)

app.include_router(migrate.router)
app.include_router(jobs.router)


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}
