from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

import httpx

from app.config import settings


@dataclass(frozen=True)
class PaymentRequest:
    id: int
    external_id: str
    execute_on: date
    amount: Decimal
    currency: str
    payload: dict[str, Any]
    factory_request_id: UUID
    attempts: int


class FactoryError(RuntimeError):
    """A factory request failed and can be retried."""


def build_factory_payload(payment: PaymentRequest) -> dict[str, Any]:
    """Build the stable request body sent to the payment factory."""
    return {
        "payment_id": str(payment.id),
        "external_id": payment.external_id,
        "execute_on": payment.execute_on.isoformat(),
        "amount": str(Decimal(payment.amount)),
        "currency": payment.currency,
        "data": payment.payload,
    }


async def execute_in_factory(
    client: httpx.AsyncClient, payment: PaymentRequest
) -> str | None:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Idempotency-Key": str(payment.factory_request_id),
    }
    if settings.factory_token:
        headers["Authorization"] = f"Bearer {settings.factory_token}"

    try:
        response = await client.post(
            settings.factory_execute_url,
            json=build_factory_payload(payment),
            headers=headers,
            timeout=settings.http_timeout_seconds,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise FactoryError(str(exc)) from exc

    if not response.content:
        return None
    try:
        body = response.json()
    except ValueError as exc:
        raise FactoryError("Factory returned invalid JSON") from exc

    if not isinstance(body, dict):
        raise FactoryError("Factory response must be a JSON object")
    factory_payment_id = body.get("factory_payment_id") or body.get("id")
    return str(factory_payment_id) if factory_payment_id is not None else None

