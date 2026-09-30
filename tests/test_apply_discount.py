import asyncio

import pytest


async def test_apply_discount_computes_split_and_new_total(client):
    # BIG40: 40% of 29999 = 12000, capped at 7500. 75/25 split of 7500 is exact.
    response = await client.post("/orders/ord_b_2002/apply-discount", json={"code": "BIG40"})
    assert response.status_code == 200
    body = response.json()
    assert body["subtotal_paise"] == 29999
    assert body["total_paise"] == 22499
    assert body["discount"]["code"] == "BIG40"
    assert body["discount"]["discount_paise"] == 7500
    assert body["discount"]["partner_share_paise"] == 5625
    assert body["discount"]["rayy_share_paise"] == 1875


async def test_apply_discount_rounds_half_up_on_fractional_paise(client):
    # FIT12: 12% of 29999 = 3599.88 -> rounds up to 3600, under the 100000 cap.
    response = await client.post("/orders/ord_b_2001/apply-discount", json={"code": "FIT12"})
    assert response.status_code == 200
    body = response.json()
    assert body["discount"]["discount_paise"] == 3600
    assert body["total_paise"] == 26399


async def test_unknown_code_is_404(client):
    response = await client.post("/orders/ord_b_2002/apply-discount", json={"code": "NOPE"})
    assert response.status_code == 404


async def test_expired_code_is_400(client):
    response = await client.post("/orders/ord_b_2002/apply-discount", json={"code": "OLDFIT25"})
    assert response.status_code == 400


async def test_unknown_order_is_404(client):
    response = await client.post("/orders/ord_does_not_exist/apply-discount", json={"code": "FIT12"})
    assert response.status_code == 404


async def test_second_code_on_same_order_is_rejected(client):
    first = await client.post("/orders/ord_b_2004/apply-discount", json={"code": "FIT12"})
    assert first.status_code == 200

    second = await client.post("/orders/ord_b_2004/apply-discount", json={"code": "HELLO8"})
    assert second.status_code == 409

    order = await client.get("/orders/ord_b_2004")
    assert order.json()["discount"]["code"] == "FIT12"
    assert order.json()["total_paise"] == 26399


async def test_concurrent_codes_on_same_order_only_one_wins(client):
    # Two different codes race for the same order, sent at the same time.
    # Exactly one may succeed; the order must end up with exactly one
    # discount, not a mix of both.
    results = await asyncio.gather(
        client.post("/orders/ord_b_2005/apply-discount", json={"code": "FIT12"}),
        client.post("/orders/ord_b_2005/apply-discount", json={"code": "HELLO8"}),
    )
    statuses = sorted(r.status_code for r in results)
    assert statuses == [200, 409]

    order = await client.get("/orders/ord_b_2005")
    discount = order.json()["discount"]
    assert discount["code"] in {"FIT12", "HELLO8"}


async def test_cannot_apply_discount_to_a_paid_order(client):
    payment_response = await _pay(client, "ord_b_2003", 64950)
    assert payment_response["status"] == "ok"

    response = await client.post("/orders/ord_b_2003/apply-discount", json={"code": "FIT12"})
    assert response.status_code == 409


async def _pay(client, order_id: str, amount_paise: int) -> dict:
    from app.gateway import SIGNATURE_HEADER, StubGateway
    from app.config import settings

    gateway = StubGateway(webhook_secret=settings.gateway_webhook_secret)
    payment = gateway.create_payment(order_id, amount_paise)
    body = gateway.webhook_body(payment)
    signature = gateway.sign(body)
    response = await client.post(
        "/webhooks/payment",
        content=body,
        headers={SIGNATURE_HEADER: signature, "Content-Type": "application/json"},
    )
    return response.json()
