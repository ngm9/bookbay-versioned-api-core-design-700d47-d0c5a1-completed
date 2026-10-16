import hashlib
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import errors, models, notifications, schemas
from app.auth import AuthUser, get_current_user
from app.db import get_db

router = APIRouter()


@router.post("/registerUser", tags=["users"])
def register_user(payload: schemas.UserCreate, db: Session = Depends(get_db)):
    if db.query(models.User).filter(models.User.email == payload.email).first():
        return errors.bad_request("email_exists", "An account already uses this email")
    user = models.User(email=payload.email, display_name=payload.display_name, phone=payload.phone)
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"userId": user.id, "email": user.email, "displayName": user.display_name}


@router.get("/getUser", tags=["users"])
def get_user(current: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    user = db.get(models.User, current.id)
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "phone": user.phone,
        "role": user.role,
        "created_at": user.created_at.isoformat(),
    }


@router.put("/updateUser", tags=["users"])
def update_user(payload: schemas.UserUpdate, current: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    user = db.get(models.User, current.id)
    values = payload.model_dump(exclude_unset=True)
    for key, value in values.items():
        setattr(user, key, value)
    db.commit()
    return {"success": True, "user": {"userId": user.id, "displayName": user.display_name, "phone": user.phone}}


@router.delete("/deleteUser", tags=["users"])
def delete_user(current: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    user = db.get(models.User, current.id)
    user.active = False
    db.commit()
    return {"status": "deleted"}


@router.post("/addresses", tags=["users"])
def add_address(payload: schemas.AddressCreate, current: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    address = models.Address(user_id=current.id, **payload.model_dump())
    db.add(address)
    db.commit()
    return {"addressId": address.id, **payload.model_dump()}


@router.get("/addresses", tags=["users"])
def get_addresses(current: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(models.Address).filter(models.Address.user_id == current.id).all()
    return [{"id": a.id, "label": a.label, "line1": a.line1, "line2": a.line2, "city": a.city, "region": a.region, "postalCode": a.postal_code, "country": a.country} for a in rows]


@router.put("/addresses/{address_id}", tags=["users"])
def update_address(address_id: str, payload: dict[str, Any], current: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    address = db.get(models.Address, address_id)
    if address is None:
        return errors.not_found("address", address_id)
    if address.user_id != current.id:
        return errors.forbidden()
    allowed = {"label", "line1", "line2", "city", "region", "postal_code", "country"}
    for key, value in payload.items():
        if key in allowed:
            setattr(address, key, value)
    db.commit()
    return {"ok": True, "address_id": address.id}


@router.delete("/addresses/{address_id}", tags=["users"])
def delete_address(address_id: str, current: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    address = db.get(models.Address, address_id)
    if not address or address.user_id != current.id:
        raise HTTPException(status_code=404, detail="Address not found")
    db.delete(address)
    db.commit()
    return {"success": 1}


@router.post("/createCart", tags=["orders"])
def create_cart(current: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    cart = models.Cart(user_id=current.id)
    db.add(cart)
    db.commit()
    return {"cartId": cart.id, "version": cart.version}


@router.get("/cart/{cart_id}", tags=["orders"])
def get_cart(cart_id: str, current: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    cart = db.get(models.Cart, cart_id)
    if cart is None:
        return {"error": "Cart does not exist"}
    if cart.user_id != current.id:
        raise HTTPException(status_code=403, detail="Not your cart")
    items = db.query(models.CartItem, models.Listing, models.Book).join(models.Listing, models.CartItem.listing_id == models.Listing.id).join(models.Book, models.Listing.book_id == models.Book.id).filter(models.CartItem.cart_id == cart.id).all()
    return {"cart_id": cart.id, "version": cart.version, "items": [{"listingId": item.listing_id, "title": book.title, "qty": item.quantity, "price": float(listing.price)} for item, listing, book in items]}


@router.post("/cart/{cart_id}/items", tags=["orders"])
def add_cart_item(cart_id: str, payload: schemas.CartItemRequest, current: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    cart = db.get(models.Cart, cart_id)
    listing = db.get(models.Listing, payload.listing_id)
    if cart is None or cart.user_id != current.id:
        return errors.not_found("cart", cart_id)
    if listing is None or listing.status != "active" or listing.quantity < payload.quantity:
        return errors.bad_request("listing_unavailable", "The listing cannot satisfy this quantity")
    item = db.query(models.CartItem).filter(models.CartItem.cart_id == cart_id, models.CartItem.listing_id == payload.listing_id).first()
    if item:
        item.quantity += payload.quantity
    else:
        item = models.CartItem(cart_id=cart_id, listing_id=payload.listing_id, quantity=payload.quantity)
        db.add(item)
    cart.version += 1
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return errors.bad_request("cart_conflict", "Cart was updated concurrently")
    return {"cartId": cart.id, "itemId": item.id, "version": cart.version}


@router.put("/cart/{cart_id}/items/{item_id}", tags=["orders"])
def update_cart_item(cart_id: str, item_id: str, payload: dict[str, Any], current: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    cart = db.get(models.Cart, cart_id)
    item = db.get(models.CartItem, item_id)
    if not cart or cart.user_id != current.id or not item or item.cart_id != cart.id:
        raise HTTPException(status_code=404, detail="cart item not found")
    quantity = int(payload.get("quantity", 0))
    if quantity <= 0:
        db.delete(item)
    else:
        item.quantity = quantity
    cart.version += 1
    db.commit()
    return {"success": True, "cartVersion": cart.version}


@router.delete("/cart/{cart_id}/items/{item_id}", tags=["orders"])
def remove_cart_item(cart_id: str, item_id: str, current: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    cart = db.get(models.Cart, cart_id)
    item = db.get(models.CartItem, item_id)
    if cart is None or cart.user_id != current.id:
        return errors.forbidden("This cart belongs to another account")
    if item is None or item.cart_id != cart_id:
        return {"error": "item_missing", "item": item_id}
    db.delete(item)
    cart.version += 1
    db.commit()
    return {"removed": item_id, "version": cart.version}


@router.post("/createOrder", tags=["orders"])
def create_order(payload: schemas.OrderCreate, background_tasks: BackgroundTasks, current: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    cart = db.query(models.Cart).filter(models.Cart.id == payload.cart_id, models.Cart.user_id == current.id).first()
    if cart is None:
        return errors.not_found("cart", payload.cart_id)
    address = db.query(models.Address).filter(models.Address.id == payload.address_id, models.Address.user_id == current.id).first()
    if address is None:
        return errors.bad_request("address_invalid", "Select an address owned by this account")
    cart_rows = db.query(models.CartItem, models.Listing, models.Book).join(models.Listing, models.CartItem.listing_id == models.Listing.id).join(models.Book, models.Listing.book_id == models.Book.id).filter(models.CartItem.cart_id == cart.id).all()
    if not cart_rows:
        return errors.bad_request("empty_cart", "Cannot create an order from an empty cart")
    total = Decimal("0.00")
    for cart_item, listing, _ in cart_rows:
        if listing.status != "active" or listing.quantity < cart_item.quantity:
            return errors.bad_request("out_of_stock", f"Listing {listing.id} is no longer available")
        total += listing.price * cart_item.quantity
    order = models.Order(user_id=current.id, cart_id=cart.id, cart_version=cart.version, address_id=address.id, total=total, status="created")
    db.add(order)
    db.flush()
    for cart_item, listing, book in cart_rows:
        db.add(models.OrderItem(order_id=order.id, listing_id=listing.id, seller_id=listing.seller_id, title=book.title, unit_price=listing.price, quantity=cart_item.quantity))
        listing.quantity -= cart_item.quantity
        if listing.quantity == 0:
            listing.status = "sold"
    db.commit()
    background_tasks.add_task(notifications.send_order_confirmation, current.id, order.id)
    return {"orderId": order.id, "cartId": cart.id, "cartVersion": cart.version, "status": order.status, "total": float(order.total), "createdAt": order.created_at.isoformat()}


@router.get("/order/{order_id}", tags=["orders"])
def get_order(order_id: str, current: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    order = db.get(models.Order, order_id)
    if not order:
        return errors.not_found("order", order_id)
    if order.user_id != current.id and current.role not in {"admin", "support"}:
        return errors.forbidden()
    items = db.query(models.OrderItem).filter(models.OrderItem.order_id == order.id).all()
    return {"id": order.id, "user_id": order.user_id, "cart_id": order.cart_id, "status": order.status, "total": str(order.total), "items": [{"listing_id": i.listing_id, "title": i.title, "quantity": i.quantity, "unit_price": str(i.unit_price)} for i in items]}


@router.get("/getUserOrders", tags=["orders"])
def get_user_orders(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100), current: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    query = db.query(models.Order).filter(models.Order.user_id == current.id)
    total = query.count()
    orders = query.order_by(models.Order.created_at.desc()).offset((page - 1) * size).limit(size).all()
    return {"page": page, "size": size, "total": total, "orders": [{"orderId": o.id, "status": o.status, "amount": float(o.total), "date": o.created_at.isoformat()} for o in orders]}


@router.post("/order/{order_id}/pay", tags=["orders"])
def pay_order(order_id: str, payload: schemas.PaymentRequest, background_tasks: BackgroundTasks, current: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    order = db.get(models.Order, order_id)
    if order is None or order.user_id != current.id:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status not in {"created", "payment_failed"}:
        return {"error": {"code": "ORDER_STATE", "message": "Order cannot be paid"}}
    provider_reference = hashlib.sha256(payload.payment_token.encode()).hexdigest()[:24]
    payment = models.Payment(order_id=order.id, provider=payload.provider, provider_reference=provider_reference, amount=order.total, status="captured")
    order.status = "paid"
    db.add(payment)
    db.commit()
    background_tasks.add_task(notifications.send_payment_confirmation, current.id, order.id)
    return {"payment_id": payment.id, "order_id": order.id, "status": "captured"}


@router.get("/payments/{payment_id}", tags=["orders"])
def get_payment(payment_id: str, current: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    payment = db.get(models.Payment, payment_id)
    if payment is None:
        return errors.not_found("payment", payment_id)
    order = db.get(models.Order, payment.order_id)
    if order.user_id != current.id and current.role != "admin":
        return errors.forbidden()
    return {"paymentId": payment.id, "orderId": payment.order_id, "provider": payment.provider, "amount": float(payment.amount), "status": payment.status}


@router.post("/favorites/{listing_id}", tags=["users"])
def add_favorite(listing_id: str, current: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    favorite = models.Favorite(user_id=current.id, listing_id=listing_id)
    db.add(favorite)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
    return {"success": True, "listingId": listing_id}


@router.delete("/favorites/{listing_id}", tags=["users"])
def remove_favorite(listing_id: str, current: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    favorite = db.query(models.Favorite).filter(models.Favorite.user_id == current.id, models.Favorite.listing_id == listing_id).first()
    if favorite:
        db.delete(favorite)
        db.commit()
    return {"ok": True}


@router.get("/favorites", tags=["users"])
def get_favorites(current: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(models.Favorite, models.Listing, models.Book).join(models.Listing, models.Favorite.listing_id == models.Listing.id).join(models.Book, models.Listing.book_id == models.Book.id).filter(models.Favorite.user_id == current.id).all()
    return {"results": [{"listing_id": listing.id, "seller_id": listing.seller_id, "title": book.title, "price": str(listing.price)} for _, listing, book in rows]}


@router.post("/reviews", tags=["users"])
def create_review(payload: schemas.ReviewCreate, current: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    review = models.Review(user_id=current.id, book_id=payload.book_id, rating=payload.rating, body=payload.body)
    db.add(review)
    db.commit()
    return {"reviewId": review.id, "rating": review.rating}


@router.get("/books/{book_id}/reviews", tags=["users"])
def get_book_reviews(book_id: str, db: Session = Depends(get_db)):
    rows = db.query(models.Review, models.User).join(models.User, models.Review.user_id == models.User.id).filter(models.Review.book_id == book_id).order_by(models.Review.created_at.desc()).all()
    average = db.query(func.avg(models.Review.rating)).filter(models.Review.book_id == book_id).scalar()
    return {"bookId": book_id, "averageRating": float(average or 0), "reviews": [{"id": review.id, "user": user.display_name, "rating": review.rating, "body": review.body} for review, user in rows]}


@router.get("/admin/orders", tags=["orders"])
def admin_orders(status: str | None = None, current: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    if current.role not in {"admin", "support"}:
        return errors.forbidden("Operations access required")
    query = db.query(models.Order)
    if status:
        query = query.filter(models.Order.status == status)
    rows = query.order_by(models.Order.created_at.desc()).limit(200).all()
    return [{"id": o.id, "userId": o.user_id, "cart": o.cart_id, "cartVersion": o.cart_version, "status": o.status, "total": float(o.total)} for o in rows]
