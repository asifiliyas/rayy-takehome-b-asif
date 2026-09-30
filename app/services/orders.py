"""Order business rules. No HTTP here; routes call into this module."""

from datetime import datetime, timezone

from app.models import Order
from app.repositories import discount_codes as discount_codes_repo
from app.repositories import orders as orders_repo
from app.services import pricing


class OrderNotFound(Exception):
    pass


class OrderAlreadyPaid(Exception):
    pass


class DiscountAlreadyApplied(Exception):
    pass


class DiscountCodeInvalid(Exception):
    pass


class DiscountCodeExpired(Exception):
    pass


class PaymentAmountMismatch(Exception):
    pass


class PaymentConflict(Exception):
    pass


async def get_order(order_id: str) -> Order:
    doc = await orders_repo.get(order_id)
    if doc is None:
        raise OrderNotFound(order_id)
    return Order(**doc)


async def list_orders(limit: int = 50) -> list[Order]:
    return [Order(**doc) for doc in await orders_repo.list_recent(limit)]


async def apply_discount(order_id: str, code: str) -> Order:
    order_doc = await orders_repo.get(order_id)
    if order_doc is None:
        raise OrderNotFound(order_id)
    if order_doc["status"] == "paid":
        raise OrderAlreadyPaid(order_id)
    if order_doc.get("discount") is not None:
        raise DiscountAlreadyApplied(order_id)

    discount_code = discount_codes_repo.get_by_code(code)
    if discount_code is None:
        raise DiscountCodeInvalid(code)
    now = datetime.now(timezone.utc)
    if discount_code.expires_at <= now:
        raise DiscountCodeExpired(code)

    subtotal_paise = order_doc["subtotal_paise"]
    discount_paise = pricing.compute_discount(
        subtotal_paise, discount_code.percent_off_bps, discount_code.cap_paise
    )
    partner_share_paise, rayy_share_paise = pricing.split_discount(
        discount_paise, discount_code.partner_share_bps
    )
    discount_record = {
        "code": discount_code.code,
        "percent_off_bps": discount_code.percent_off_bps,
        "cap_paise": discount_code.cap_paise,
        "discount_paise": discount_paise,
        "partner_share_bps": discount_code.partner_share_bps,
        "rayy_share_bps": discount_code.rayy_share_bps,
        "partner_share_paise": partner_share_paise,
        "rayy_share_paise": rayy_share_paise,
        "applied_at": now,
    }
    total_paise = subtotal_paise - discount_paise

    updated = await orders_repo.apply_discount_atomic(order_id, discount_record, total_paise)
    if updated is None:
        # Lost the race: another request applied a code (or paid the order)
        # between our read and our write.
        raise DiscountAlreadyApplied(order_id)
    return Order(**updated)


async def record_payment(order_id: str, payment_id: str, amount_paise: int) -> Order:
    order_doc = await orders_repo.get(order_id)
    if order_doc is None:
        raise OrderNotFound(order_id)

    existing_payment = order_doc.get("payment")
    if existing_payment is not None:
        if existing_payment["payment_id"] == payment_id:
            return Order(**order_doc)  # duplicate delivery of the same event
        raise PaymentConflict(order_id)

    if amount_paise != order_doc["total_paise"]:
        raise PaymentAmountMismatch(order_id)

    payment_record = {
        "payment_id": payment_id,
        "amount_paise": amount_paise,
        "received_at": datetime.now(timezone.utc),
    }
    updated = await orders_repo.record_payment_atomic(order_id, payment_record)
    if updated is None:
        # Lost the race: another delivery recorded a payment between our
        # read and our write. Re-check rather than assume a conflict.
        refreshed = await orders_repo.get(order_id)
        if refreshed and refreshed["payment"]["payment_id"] == payment_id:
            return Order(**refreshed)
        raise PaymentConflict(order_id)
    return Order(**updated)
