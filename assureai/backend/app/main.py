"""Thin FastAPI app for the AssureAI test harness UI.

Wires up app.api.routes only - no auth, no database (none exists for
AssureAI yet), matching the "minimal test interface" scope.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router

app = FastAPI(title="AssureAI Test Harness API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5174", "http://127.0.0.1:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
