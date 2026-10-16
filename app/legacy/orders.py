from app.models import Order


def legacy_create_order_response(order: Order, cart_id: str, cart_version: int) -> dict[str, object]:
    return {
        "orderId": order.id,
        "cartId": cart_id,
        "cartVersion": cart_version,
        "status": order.status,
        "total": float(order.total),
        "createdAt": order.created_at.isoformat(),
    }
