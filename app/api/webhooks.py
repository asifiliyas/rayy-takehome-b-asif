import json

from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError

from app.gateway import SIGNATURE_HEADER, StubGateway
from app.models import PaymentWebhookBody
from app.services import orders as orders_service

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
_gateway = StubGateway()


@router.post("/payment")
async def payment_webhook(request: Request) -> dict:
    raw_body = await request.body()
    signature = request.headers.get(SIGNATURE_HEADER)
    if not signature or not _gateway.verify(raw_body, signature):
        raise HTTPException(status_code=401, detail="invalid webhook signature")

    try:
        payload = PaymentWebhookBody(**json.loads(raw_body))
    except (json.JSONDecodeError, ValidationError):
        raise HTTPException(status_code=400, detail="malformed webhook body")

    try:
        order = await orders_service.record_payment(
            payload.order_id, payload.payment_id, payload.amount_paise
        )
    except orders_service.OrderNotFound:
        raise HTTPException(status_code=404, detail="order not found")
    except orders_service.PaymentConflict:
        raise HTTPException(status_code=409, detail="a different payment is already recorded")
    except orders_service.PaymentAmountMismatch:
        # Acknowledge receipt (200) so the gateway does not retry forever —
        # retrying will not fix a mismatched amount — but do not mark the
        # order paid. See NOTES.md: this needs a real reconciliation/alert
        # path in production, which this exercise does not build.
        return {"status": "amount_mismatch", "order_id": payload.order_id}

    return {"status": "ok", "order_id": order.order_id, "order_status": order.status}
