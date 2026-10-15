from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import or_, select

from app.config import settings
from app.db import SessionLocal
from app.factory import FactoryError, PaymentRequest, execute_in_factory
from app.models import Payment, PaymentStatus


logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def business_date() -> date:
    return datetime.now(ZoneInfo(settings.app_timezone)).date()


def claim_due_payments(today: date) -> list[PaymentRequest]:
    """Claim a bounded batch so another Pod can safely process other rows."""
    now = utc_now()
    stale_before = now - timedelta(seconds=settings.processing_lease_seconds)
    retryable = (
        (Payment.status.in_((PaymentStatus.PENDING.value, PaymentStatus.QUEUED.value)))
        & or_(Payment.next_attempt_at.is_(None), Payment.next_attempt_at <= now)
    )
    stale_processing = (
        (Payment.status == PaymentStatus.PROCESSING.value)
        & (Payment.processing_started_at <= stale_before)
    )

    claimed: list[PaymentRequest] = []
    with SessionLocal.begin() as session:
        payments = session.scalars(
            select(Payment)
            .where(
                Payment.execute_on <= today,
                or_(retryable, stale_processing),
            )
            .order_by(Payment.execute_on, Payment.id)
            .limit(settings.max_concurrency)
            .with_for_update(skip_locked=True)
        ).all()

        for payment in payments:
            payment.status = PaymentStatus.PROCESSING.value
            payment.processing_started_at = now
            payment.next_attempt_at = None
            payment.attempts += 1
            payment.last_error = None
            payment.updated_at = now
            claimed.append(
                PaymentRequest(
                    id=payment.id,
                    external_id=payment.external_id,
                    execute_on=payment.execute_on,
                    amount=payment.amount,
                    currency=payment.currency,
                    payload=payment.payload,
                    factory_request_id=payment.factory_request_id,
                    attempts=payment.attempts,
                )
            )
    return claimed


def mark_submitted(payment_id: int, factory_payment_id: str | None) -> None:
    now = utc_now()
    with SessionLocal.begin() as session:
        payment = session.get(Payment, payment_id, with_for_update=True)
        if payment is None or payment.status == PaymentStatus.SUBMITTED.value:
            return
        payment.status = PaymentStatus.SUBMITTED.value
        payment.factory_payment_id = factory_payment_id
        payment.submitted_at = now
        payment.processing_started_at = None
        payment.next_attempt_at = None
        payment.last_error = None
        payment.updated_at = now


def mark_retry(payment_id: int, error: str, delay_seconds: int) -> None:
    now = utc_now()
    with SessionLocal.begin() as session:
        payment = session.get(Payment, payment_id, with_for_update=True)
        if payment is None:
            return
        payment.status = PaymentStatus.PENDING.value
        payment.processing_started_at = None
        payment.next_attempt_at = now + timedelta(seconds=delay_seconds)
        payment.last_error = error[:4000]
        payment.updated_at = now


def mark_failed(payment_id: int, error: str) -> None:
    now = utc_now()
    with SessionLocal.begin() as session:
        payment = session.get(Payment, payment_id, with_for_update=True)
        if payment is None:
            return
        payment.status = PaymentStatus.FAILED.value
        payment.processing_started_at = None
        payment.last_error = error[:4000]
        payment.updated_at = now


async def _handle_payment(client: httpx.AsyncClient, payment: PaymentRequest) -> None:
    try:
        factory_payment_id = await execute_in_factory(client, payment)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        if not isinstance(exc, FactoryError):
            logger.exception("Unexpected payment execution error", extra={"payment_id": payment.id})
        else:
            logger.warning("Factory request failed", extra={"payment_id": payment.id, "error": str(exc)})

        max_attempts = settings.max_retries + 1
        if payment.attempts >= max_attempts:
            await asyncio.to_thread(mark_failed, payment.id, str(exc))
            return

        delay_seconds = min(60 * (2 ** (payment.attempts - 1)), 3600)
        await asyncio.to_thread(mark_retry, payment.id, str(exc), delay_seconds)
        return

    await asyncio.to_thread(mark_submitted, payment.id, factory_payment_id)


async def run_payment_loop(stop_event: asyncio.Event) -> None:
    """Poll PostgreSQL until FastAPI begins its shutdown sequence."""
    async with httpx.AsyncClient(
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        timeout=settings.http_timeout_seconds,
    ) as client:
        while not stop_event.is_set():
            try:
                payments = await asyncio.to_thread(claim_due_payments, business_date())
                if payments:
                    await asyncio.gather(
                        *(_handle_payment(client, payment) for payment in payments)
                    )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Payment polling iteration failed")

            try:
                await asyncio.wait_for(
                    stop_event.wait(), timeout=settings.poll_interval_seconds
                )
            except asyncio.TimeoutError:
                pass


def check_database_connection() -> None:
    with SessionLocal() as session:
        session.execute(select(1))

