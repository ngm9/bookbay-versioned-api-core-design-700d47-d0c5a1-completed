import logging

from app.db import SessionLocal
from app.models import Notification

logger = logging.getLogger("bookbay.notifications")


def _record(user_id: str, kind: str, message: str) -> None:
    with SessionLocal() as db:
        notification = Notification(user_id=user_id, kind=kind, message=message)
        db.add(notification)
        db.commit()
        logger.info("notification_created user_id=%s kind=%s", user_id, kind)


def send_order_confirmation(user_id: str, order_id: str) -> None:
    _record(user_id, "order_confirmation", f"Your order {order_id} has been created.")


def send_payment_confirmation(user_id: str, order_id: str) -> None:
    _record(user_id, "payment_confirmation", f"Payment for order {order_id} was accepted.")


def send_cancellation_notice(user_id: str, order_id: str) -> None:
    _record(user_id, "order_cancelled", f"Order {order_id} has been cancelled.")


def send_refund_notice(user_id: str, refund_id: str, status: str) -> None:
    _record(user_id, "refund_update", f"Refund {refund_id} is now {status}.")
