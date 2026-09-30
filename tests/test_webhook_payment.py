from app.config import settings
from app.gateway import SIGNATURE_HEADER, StubGateway


def _deliver(client, payment: dict, gateway: StubGateway):
    body = gateway.webhook_body(payment)
    signature = gateway.sign(body)
    return client.post(
        "/webhooks/payment",
        content=body,
        headers={SIGNATURE_HEADER: signature, "Content-Type": "application/json"},
    )


async def test_webhook_marks_order_paid(client):
    gateway = StubGateway(webhook_secret=settings.gateway_webhook_secret)
    payment = {"payment_id": "pay_b_8001", "order_id": "ord_b_2003", "amount_paise": 64950}

    response = await _deliver(client, payment, gateway)
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "order_id": "ord_b_2003", "order_status": "paid"}

    order = await client.get("/orders/ord_b_2003")
    body = order.json()
    assert body["status"] == "paid"
    assert body["payment"]["payment_id"] == "pay_b_8001"


async def test_duplicate_delivery_of_same_payment_is_idempotent(client):
    gateway = StubGateway(webhook_secret=settings.gateway_webhook_secret)
    payment = {"payment_id": "pay_b_8001", "order_id": "ord_b_2003", "amount_paise": 64950}

    first = await _deliver(client, payment, gateway)
    second = await _deliver(client, payment, gateway)
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["order_status"] == "paid"

    order = await client.get("/orders/ord_b_2003")
    assert order.json()["payment"]["payment_id"] == "pay_b_8001"


async def test_amount_mismatch_does_not_mark_order_paid(client):
    # A payment for the pre-discount amount arriving after a discount was
    # applied: the gateway charged 29999 but the order's total is now 26399.
    await client.post("/orders/ord_b_2001/apply-discount", json={"code": "FIT12"})

    gateway = StubGateway(webhook_secret=settings.gateway_webhook_secret)
    payment = {"payment_id": "pay_b_8002", "order_id": "ord_b_2001", "amount_paise": 29999}
    response = await _deliver(client, payment, gateway)

    assert response.status_code == 200
    assert response.json()["status"] == "amount_mismatch"

    order = await client.get("/orders/ord_b_2001")
    assert order.json()["status"] == "pending"
    assert order.json()["payment"] is None


async def test_wrong_signature_is_rejected(client):
    gateway = StubGateway(webhook_secret=settings.gateway_webhook_secret)
    payment = {"payment_id": "pay_bad", "order_id": "ord_b_2003", "amount_paise": 64950}
    body = gateway.webhook_body(payment)
    response = await client.post(
        "/webhooks/payment",
        content=body,
        headers={SIGNATURE_HEADER: "not-a-real-signature", "Content-Type": "application/json"},
    )
    assert response.status_code == 401


async def test_unknown_order_is_404(client):
    gateway = StubGateway(webhook_secret=settings.gateway_webhook_secret)
    payment = {"payment_id": "pay_x", "order_id": "ord_does_not_exist", "amount_paise": 100}
    response = await _deliver(client, payment, gateway)
    assert response.status_code == 404


async def test_different_payment_id_for_already_paid_order_is_conflict(client):
    gateway = StubGateway(webhook_secret=settings.gateway_webhook_secret)
    payment = {"payment_id": "pay_first", "order_id": "ord_b_2003", "amount_paise": 64950}
    await _deliver(client, payment, gateway)

    other_payment = {"payment_id": "pay_second", "order_id": "ord_b_2003", "amount_paise": 64950}
    response = await _deliver(client, other_payment, gateway)
    assert response.status_code == 409
