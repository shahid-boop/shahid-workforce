"""FastAPI entrypoint for the Shahid AI workforce service."""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="Shahid AI Workforce", version="0.1.0")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}