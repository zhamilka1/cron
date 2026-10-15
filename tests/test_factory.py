from datetime import date
from decimal import Decimal
from uuid import uuid4

from app.factory import PaymentRequest, build_factory_payload


def test_factory_payload_is_stable_and_json_friendly() -> None:
    payment = PaymentRequest(
        id=42,
        external_id="order-10001",
        execute_on=date(2026, 10, 15),
        amount=Decimal("1250.00"),
        currency="RUB",
        payload={"payee_account": "40817810000000000002"},
        factory_request_id=uuid4(),
        attempts=1,
    )

    assert build_factory_payload(payment) == {
        "payment_id": "42",
        "external_id": "order-10001",
        "execute_on": "2026-10-15",
        "amount": "1250.00",
        "currency": "RUB",
        "data": {"payee_account": "40817810000000000002"},
    }

