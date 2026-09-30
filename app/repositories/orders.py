"""All database access for the ``orders`` collection."""

from pymongo import ReturnDocument

from app.db import ORDERS, get_db


def _to_order_dict(doc: dict) -> dict:
    doc = dict(doc)
    doc["order_id"] = doc.pop("_id")
    return doc


async def get(order_id: str) -> dict | None:
    doc = await get_db()[ORDERS].find_one({"_id": order_id})
    return _to_order_dict(doc) if doc else None


async def list_recent(limit: int = 50) -> list[dict]:
    cursor = get_db()[ORDERS].find({}).sort("created_at", -1).limit(limit)
    return [_to_order_dict(doc) async for doc in cursor]


async def apply_discount_atomic(order_id: str, discount: dict, total_paise: int) -> dict | None:
    """Set ``discount`` and ``total_paise`` iff the order still has no
    discount and is not paid. Returns the updated order, or ``None`` if the
    condition no longer held (someone else applied a code, or paid, first) —
    the single filtered update is what keeps concurrent apply-discount
    requests from both succeeding."""
    doc = await get_db()[ORDERS].find_one_and_update(
        {"_id": order_id, "discount": {"$exists": False}, "status": {"$ne": "paid"}},
        {"$set": {"discount": discount, "total_paise": total_paise}},
        return_document=ReturnDocument.AFTER,
    )
    return _to_order_dict(doc) if doc else None


async def record_payment_atomic(order_id: str, payment: dict) -> dict | None:
    """Set ``payment`` and mark the order paid iff no payment is recorded
    yet. Returns the updated order, or ``None`` if a payment was already
    recorded (duplicate webhook delivery, or a genuine conflict — the caller
    distinguishes those by comparing payment ids)."""
    doc = await get_db()[ORDERS].find_one_and_update(
        {"_id": order_id, "payment": {"$exists": False}},
        {"$set": {"payment": payment, "status": "paid"}},
        return_document=ReturnDocument.AFTER,
    )
    return _to_order_dict(doc) if doc else None
