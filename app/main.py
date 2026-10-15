from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException

from app.config import settings
from app.executor import check_database_connection, run_payment_loop


logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    stop_event = asyncio.Event()
    payment_loop = asyncio.create_task(run_payment_loop(stop_event))
    app.state.payment_loop = payment_loop

    try:
        yield
    finally:
        stop_event.set()
        try:
            await asyncio.wait_for(
                payment_loop, timeout=settings.shutdown_timeout_seconds
            )
        except asyncio.TimeoutError:
            payment_loop.cancel()
            await asyncio.gather(payment_loop, return_exceptions=True)


app = FastAPI(
    title="Payment Executor",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health/live")
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
async def readiness() -> dict[str, str]:
    try:
        await asyncio.to_thread(check_database_connection)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="database is unavailable") from exc
    return {"status": "ok"}

