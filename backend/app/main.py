"""
FastAPI application entry point.

Creates the app instance, includes all routers, adds middleware and
exception handlers, and sets up the database on startup via lifespan.

Requirements: 2.1
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.db import init_db

logger = logging.getLogger(__name__)


# ============================================================================
# Lifespan — startup/shutdown hooks
# ============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan context manager.

    On startup: create database tables if they don't exist.
    On shutdown: (nothing needed — connection pool handles cleanup).
    """
    logger.info("Starting up — initializing database tables...")
    init_db()
    logger.info("Database tables ready.")
    yield
    logger.info("Shutting down.")


# ============================================================================
# App instance
# ============================================================================


app = FastAPI(
    title="Autonomous Scheduler API",
    description="AI-powered task scheduling and calendar management via natural language.",
    version="0.1.0",
    lifespan=lifespan,
)


# ============================================================================
# CORS middleware
# ============================================================================

# ALLOWED_ORIGINS env var: comma-separated list of frontend URLs.
# Defaults to * for local dev; set in production to your Vercel URL.
import os
_origins = os.environ.get("ALLOWED_ORIGINS", "*").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Global exception handlers
# ============================================================================


@app.exception_handler(ValidationError)
async def validation_error_handler(request: Request, exc: ValidationError):
    """Return HTTP 422 for Pydantic validation errors."""
    return JSONResponse(
        status_code=422,
        content={
            "detail": "Validation error",
            "errors": exc.errors(),
        },
    )


@app.exception_handler(ConnectionError)
async def llm_connection_error_handler(request: Request, exc: ConnectionError):
    """Return HTTP 503 for LLM/external service connection errors."""
    logger.error("LLM/external service unavailable: %s", exc)
    return JSONResponse(
        status_code=503,
        content={
            "detail": "External service temporarily unavailable. Please retry.",
            "retry_after": 30,
        },
    )


@app.exception_handler(OSError)
async def db_error_handler(request: Request, exc: OSError):
    """Return HTTP 500 for database connection errors."""
    logger.error("Database error: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error. Please try again later."},
    )


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception):
    """Catch-all for unhandled exceptions — return HTTP 500."""
    logger.error("Unhandled exception: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error."},
    )


# ============================================================================
# Include routers
# ============================================================================

from app.routers.chat import router as chat_router
from app.routers.tasks import router as tasks_router
from app.routers.preferences import router as preferences_router
from app.routers.calendar import router as calendar_router
from app.routers.api_keys import router as api_keys_router
from app.routers.telegram_bot import router as telegram_router
from app.routers.calendar_sync import router as calendar_sync_router
from app.routers.billing import router as billing_router

app.include_router(chat_router)
app.include_router(tasks_router)
app.include_router(preferences_router)
app.include_router(calendar_router)
app.include_router(api_keys_router)
app.include_router(telegram_router)
app.include_router(calendar_sync_router)
app.include_router(billing_router)


# ============================================================================
# Health check
# ============================================================================


@app.get("/health", tags=["health"])
def health_check():
    """Simple health check endpoint."""
    return {"status": "ok"}
