from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.legacy.orders import legacy_create_order_response
from app.models import Cart, CartItem, IdempotencyRecord, Listing, Order, OrderItem


class OrderServiceError(Exception):
    def __init__(self, code: str, message: str, http_status: int = 400) -> None:
        self.code = code
        self.message = message
        self.http_status = http_status
        super().__init__(message)


@dataclass(frozen=True)
class CreateOrderResult:
    order: Order
    cart_id: str
    cart_version: int
    is_new: bool

    def legacy_body(self) -> dict[str, object]:
        return legacy_create_order_response(self.order, self.cart_id, self.cart_version)


def _request_hash(user_id: str, cart_id: str, address_id: str) -> str:
    payload = f"{user_id}|{cart_id}|{address_id}"
    return hashlib.sha256(payload.encode()).hexdigest()


def _idempotency_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=7)


class OrderService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def create_from_cart(
        self,
        *,
        user_id: str,
        cart_id: str,
        address_id: str,
        idempotency_key: str | None = None,
    ) -> CreateOrderResult:
        if idempotency_key:
            replay = self._check_idempotency(
                user_id=user_id,
                key=idempotency_key,
                cart_id=cart_id,
                address_id=address_id,
            )
            if replay is not None:
                return replay

        existing = self._find_order_by_cart_snapshot(user_id=user_id, cart_id=cart_id)
        if existing is not None:
            cart = self._db.get(Cart, cart_id)
            cart_version = cart.version if cart else existing.cart_version
            return CreateOrderResult(
                order=existing,
                cart_id=cart_id,
                cart_version=cart_version,
                is_new=False,
            )

        try:
            result = self._commit_new_order(user_id=user_id, cart_id=cart_id, address_id=address_id)
        except IntegrityError:
            self._db.rollback()
            existing = self._find_order_by_cart_snapshot(user_id=user_id, cart_id=cart_id)
            if existing is None:
                raise
            cart = self._db.get(Cart, cart_id)
            cart_version = cart.version if cart else existing.cart_version
            return CreateOrderResult(
                order=existing,
                cart_id=cart_id,
                cart_version=cart_version,
                is_new=False,
            )

        if idempotency_key:
            self._store_idempotency(
                user_id=user_id,
                key=idempotency_key,
                cart_id=cart_id,
                address_id=address_id,
                body=result.legacy_body(),
            )
        return result

    def _check_idempotency(
        self,
        *,
        user_id: str,
        key: str,
        cart_id: str,
        address_id: str,
    ) -> CreateOrderResult | None:
        record = (
            self._db.query(IdempotencyRecord)
            .filter(IdempotencyRecord.user_id == user_id, IdempotencyRecord.key == key)
            .first()
        )
        if record is None:
            return None
        expires_at = record.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < datetime.now(timezone.utc):
            self._db.delete(record)
            self._db.flush()
            return None

        expected = _request_hash(user_id, cart_id, address_id)
        if record.request_hash != expected:
            raise OrderServiceError(
                "idempotency_key_mismatch",
                "Idempotency-Key was already used with a different request body",
                http_status=409,
            )

        body = json.loads(record.response_body)
        order = self._db.get(Order, record.resource_id)
        if order is None:
            raise OrderServiceError("idempotency_corrupt", "Stored idempotency record is invalid", http_status=500)
        return CreateOrderResult(
            order=order,
            cart_id=str(body["cartId"]),
            cart_version=int(body["cartVersion"]),
            is_new=False,
        )

    def _store_idempotency(
        self,
        *,
        user_id: str,
        key: str,
        cart_id: str,
        address_id: str,
        body: dict[str, object],
    ) -> None:
        record = IdempotencyRecord(
            user_id=user_id,
            key=key,
            request_hash=_request_hash(user_id, cart_id, address_id),
            response_status=200,
            response_body=json.dumps(body),
            resource_id=str(body["orderId"]),
            expires_at=_idempotency_expiry(),
        )
        self._db.add(record)
        try:
            self._db.commit()
        except IntegrityError:
            self._db.rollback()

    def _find_order_by_cart_snapshot(self, *, user_id: str, cart_id: str) -> Order | None:
        cart = self._db.get(Cart, cart_id)
        if cart is None:
            return None
        return (
            self._db.query(Order)
            .filter(
                Order.user_id == user_id,
                Order.cart_id == cart_id,
                Order.cart_version == cart.version,
            )
            .first()
        )

    def _commit_new_order(self, *, user_id: str, cart_id: str, address_id: str) -> CreateOrderResult:
        from app import models

        cart = self._db.query(Cart).filter(Cart.id == cart_id, Cart.user_id == user_id).first()
        if cart is None:
            raise OrderServiceError("cart_not_found", f"Cart {cart_id} was not found", http_status=404)

        address = (
            self._db.query(models.Address)
            .filter(models.Address.id == address_id, models.Address.user_id == user_id)
            .first()
        )
        if address is None:
            raise OrderServiceError(
                "address_invalid",
                "Select an address owned by this account",
                http_status=400,
            )

        cart_rows = (
            self._db.query(CartItem, Listing, models.Book)
            .join(Listing, CartItem.listing_id == Listing.id)
            .join(models.Book, Listing.book_id == models.Book.id)
            .filter(CartItem.cart_id == cart.id)
            .all()
        )
        if not cart_rows:
            raise OrderServiceError("empty_cart", "Cannot create an order from an empty cart", http_status=400)

        total = Decimal("0.00")
        for cart_item, listing, _ in cart_rows:
            if listing.status != "active" or listing.quantity < cart_item.quantity:
                raise OrderServiceError(
                    "out_of_stock",
                    f"Listing {listing.id} is no longer available",
                    http_status=400,
                )
            total += listing.price * cart_item.quantity

        order = Order(
            user_id=user_id,
            cart_id=cart.id,
            cart_version=cart.version,
            address_id=address.id,
            total=total,
            status="created",
        )
        self._db.add(order)
        self._db.flush()

        for cart_item, listing, book in cart_rows:
            self._db.add(
                OrderItem(
                    order_id=order.id,
                    listing_id=listing.id,
                    seller_id=listing.seller_id,
                    title=book.title,
                    unit_price=listing.price,
                    quantity=cart_item.quantity,
                )
            )
            listing.quantity -= cart_item.quantity
            if listing.quantity == 0:
                listing.status = "sold"

        self._db.commit()
        self._db.refresh(order)
        return CreateOrderResult(order=order, cart_id=cart.id, cart_version=cart.version, is_new=True)
