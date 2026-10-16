import base64
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app import models, notifications, schemas
from app.auth import AuthUser, get_current_user
from app.db import get_db

router = APIRouter()


@router.post("/listings", tags=["listings"])
def create_listing(payload: schemas.ListingCreate, current: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    if current.role not in {"seller", "admin"}:
        raise HTTPException(status_code=403, detail="Seller account required")
    if db.get(models.Book, payload.book_id) is None:
        raise HTTPException(status_code=400, detail="Unknown book")
    listing = models.Listing(book_id=payload.book_id, seller_id=current.id, price=payload.price, condition=payload.condition, notes=payload.notes, quantity=payload.quantity)
    db.add(listing)
    db.commit()
    return {"id": listing.id, "bookId": listing.book_id, "sellerId": listing.seller_id, "price": float(listing.price), "condition": listing.condition, "quantity": listing.quantity}


@router.get("/listings/all", tags=["listings"])
def all_listings(cursor: str | None = None, limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    query = db.query(models.Listing, models.Book).join(models.Book, models.Listing.book_id == models.Book.id).filter(models.Listing.status == "active")
    if cursor:
        decoded = base64.urlsafe_b64decode(cursor.encode()).decode()
        query = query.filter(models.Listing.id > decoded)
    rows = query.order_by(models.Listing.id).limit(limit + 1).all()
    more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = base64.urlsafe_b64encode(rows[-1][0].id.encode()).decode() if more and rows else None
    return {"data": [{"id": listing.id, "seller_id": listing.seller_id, "book": {"id": book.id, "title": book.title, "author": book.author}, "price": str(listing.price), "condition": listing.condition} for listing, book in rows], "next_cursor": next_cursor}


@router.get("/listings/{listing_id}", tags=["listings"])
def get_listing(listing_id: str, db: Session = Depends(get_db)):
    row = db.query(models.Listing, models.Book, models.User).join(models.Book, models.Listing.book_id == models.Book.id).join(models.User, models.Listing.seller_id == models.User.id).filter(models.Listing.id == listing_id).first()
    if row is None:
        return {"error": "listing not found", "status": 404}
    listing, book, seller = row
    return {"listingId": listing.id, "sellerId": listing.seller_id, "sellerName": seller.display_name, "bookId": book.id, "title": book.title, "author": book.author, "isbn": book.isbn, "price": float(listing.price), "condition": listing.condition, "notes": listing.notes, "available": listing.quantity}


@router.patch("/listings/{listing_id}", tags=["listings"])
def update_listing(listing_id: str, payload: schemas.ListingUpdate, current: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    listing = db.get(models.Listing, listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="No listing")
    if listing.seller_id != current.id and current.role != "admin":
        return {"error": {"type": "permission", "description": "not the seller"}}
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(listing, key, value)
    if listing.quantity == 0:
        listing.status = "sold"
    db.commit()
    return {"listing_id": listing.id, "seller_id": listing.seller_id, "status": listing.status, "quantity": listing.quantity}


@router.delete("/listings/{listing_id}", tags=["listings"])
def delete_listing(listing_id: str, current: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    listing = db.get(models.Listing, listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    if listing.seller_id != current.id and current.role != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    listing.status = "deleted"
    db.commit()
    return {"success": "listing removed"}


@router.get("/seller/{seller_id}/listings", tags=["listings"])
def seller_listings(seller_id: str, include_inactive: bool = False, db: Session = Depends(get_db)):
    query = db.query(models.Listing).filter(models.Listing.seller_id == seller_id)
    if not include_inactive:
        query = query.filter(models.Listing.status == "active")
    return [{"listingId": x.id, "bookId": x.book_id, "sellerId": x.seller_id, "price": float(x.price), "state": x.status} for x in query.order_by(models.Listing.created_at.desc()).all()]


@router.get("/search", tags=["search"])
def search(q: str = "", type: str = "listing", offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100), current: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    db.add(models.SearchHistory(user_id=current.id, query=q, search_type=type))
    db.commit()
    if type == "book":
        books = db.query(models.Book).filter(or_(models.Book.title.ilike(f"%{q}%"), models.Book.author.ilike(f"%{q}%"), models.Book.isbn.ilike(f"%{q}%"))).offset(offset).limit(limit).all()
        return {"type": "book", "offset": offset, "items": [{"book_id": b.id, "title": b.title, "author": b.author, "isbn": b.isbn} for b in books]}
    rows = db.query(models.Listing, models.Book).join(models.Book, models.Listing.book_id == models.Book.id).filter(models.Listing.status == "active", or_(models.Book.title.ilike(f"%{q}%"), models.Book.author.ilike(f"%{q}%"), models.Book.isbn.ilike(f"%{q}%"))).offset(offset).limit(limit).all()
    return {"results": [{"listingId": listing.id, "sellerId": listing.seller_id, "title": book.title, "author": book.author, "price": float(listing.price)} for listing, book in rows], "offset": offset, "limit": limit}


@router.get("/search/suggestions", tags=["search"])
def search_suggestions(q: str = Query(min_length=2), db: Session = Depends(get_db)):
    books = db.query(models.Book).filter(models.Book.title.ilike(f"{q}%")).order_by(models.Book.title).limit(8).all()
    return [book.title for book in books]


@router.get("/categories", tags=["search"])
def categories(db: Session = Depends(get_db)):
    rows = db.query(models.Book.category, func.count(models.Listing.id)).outerjoin(models.Listing, models.Listing.book_id == models.Book.id).group_by(models.Book.category).order_by(models.Book.category).all()
    return {"categories": [{"name": category, "listingCount": count} for category, count in rows]}


@router.get("/book/{book_id}", tags=["search"])
def book_detail(book_id: str, db: Session = Depends(get_db)):
    book = db.get(models.Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail={"error_code": "NO_BOOK"})
    listings = db.query(models.Listing).filter(models.Listing.book_id == book.id, models.Listing.status == "active").order_by(models.Listing.price).all()
    return {"id": book.id, "isbn": book.isbn, "title": book.title, "author": book.author, "category": book.category, "edition": book.edition, "description": book.description, "offers": [{"id": item.id, "seller_id": item.seller_id, "price": str(item.price), "condition": item.condition} for item in listings]}


@router.post("/books", tags=["listings"])
def create_book(payload: dict[str, Any], current: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    if current.role not in {"seller", "admin"}:
        return {"error": "role_not_allowed"}
    required = {"isbn", "title", "author", "category"}
    if not required.issubset(payload):
        raise HTTPException(status_code=422, detail="isbn, title, author and category required")
    book = models.Book(isbn=payload["isbn"], title=payload["title"], author=payload["author"], category=payload["category"], edition=payload.get("edition"), description=payload.get("description"))
    db.add(book)
    db.commit()
    return book.__dict__ | {"_sa_instance_state": None}


@router.get("/inventory", tags=["listings"])
def inventory(current: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    if current.role not in {"seller", "admin"}:
        raise HTTPException(status_code=403, detail="seller only")
    rows = db.query(models.Listing, models.Book).join(models.Book, models.Listing.book_id == models.Book.id).filter(models.Listing.seller_id == current.id).all()
    return {"seller_id": current.id, "inventory": [{"id": listing.id, "book_title": book.title, "remaining": listing.quantity, "listing_status": listing.status} for listing, book in rows]}


@router.post("/order/{order_id}/cancelOrder", tags=["refunds"])
def cancel_order(order_id: str, background_tasks: BackgroundTasks, payload: dict[str, Any] | None = None, current: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    order = db.get(models.Order, order_id)
    if order is None:
        return {"error": "unknown_order", "orderId": order_id}
    if order.user_id != current.id and current.role not in {"admin", "support"}:
        raise HTTPException(status_code=403, detail="cannot cancel this order")
    if order.status in {"shipped", "delivered", "cancelled", "refunded"}:
        return {"error": "cannot_cancel", "currentStatus": order.status}
    items = db.query(models.OrderItem).filter(models.OrderItem.order_id == order.id).all()
    for item in items:
        listing = db.get(models.Listing, item.listing_id)
        if listing:
            listing.quantity += item.quantity
            listing.status = "active"
    order.status = "cancelled"
    db.commit()
    background_tasks.add_task(notifications.send_cancellation_notice, order.user_id, order.id)
    return {"success": True, "orderId": order.id, "reason": (payload or {}).get("reason")}


@router.get("/order/{order_id}/cancellation", tags=["refunds"])
def cancellation_status(order_id: str, current: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    order = db.get(models.Order, order_id)
    if not order or (order.user_id != current.id and current.role not in {"admin", "support"}):
        raise HTTPException(status_code=404, detail="order missing")
    return {"order_id": order.id, "cancelled": order.status == "cancelled", "state": order.status}


@router.post("/refunds", tags=["refunds"])
def request_refund(payload: dict[str, Any], current: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    order_id = payload.get("orderId") or payload.get("order_id")
    order = db.get(models.Order, order_id)
    if not order or order.user_id != current.id:
        return {"error": {"code": 404, "text": "Order does not exist"}}
    if order.status not in {"paid", "delivered", "cancelled"}:
        return {"error": "not_refundable"}
    refund = models.Refund(order_id=order.id, user_id=current.id, reason=str(payload.get("reason", "Not specified")), amount=order.total, status="requested")
    db.add(refund)
    db.commit()
    return {"refundId": refund.id, "orderId": order.id, "amount": float(refund.amount), "status": refund.status}


@router.get("/refunds/{refund_id}", tags=["refunds"])
def refund_status(refund_id: str, current: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    refund = db.get(models.Refund, refund_id)
    if refund is None:
        raise HTTPException(status_code=404, detail="Refund not found")
    if refund.user_id != current.id and current.role not in {"admin", "support"}:
        raise HTTPException(status_code=403, detail="forbidden")
    return {"id": refund.id, "order_id": refund.order_id, "requested_by": refund.user_id, "reason": refund.reason, "amount": str(refund.amount), "status": refund.status}


@router.post("/refunds/{refund_id}/approve", tags=["refunds"])
def approve_refund(refund_id: str, background_tasks: BackgroundTasks, current: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    if current.role not in {"admin", "support"}:
        return {"error": "admin_required"}
    refund = db.get(models.Refund, refund_id)
    if refund is None:
        raise HTTPException(status_code=404, detail="refund missing")
    if refund.status != "requested":
        return {"error": "wrong_state", "state": refund.status}
    refund.status = "approved"
    order = db.get(models.Order, refund.order_id)
    order.status = "refunded"
    payment = db.query(models.Payment).filter(models.Payment.order_id == order.id, models.Payment.status == "captured").first()
    if payment:
        payment.status = "refunded"
    db.commit()
    background_tasks.add_task(notifications.send_refund_notice, refund.user_id, refund.id, refund.status)
    return {"approved": True, "refund": refund.id}


@router.post("/refunds/{refund_id}/reject", tags=["refunds"])
def reject_refund(refund_id: str, background_tasks: BackgroundTasks, payload: dict[str, Any] | None = None, current: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    if current.role not in {"admin", "support"}:
        raise HTTPException(status_code=403, detail="Operations role required")
    refund = db.get(models.Refund, refund_id)
    if not refund:
        return {"errorMessage": "No such refund"}
    refund.status = "rejected"
    if payload and payload.get("reason"):
        refund.reason = f"{refund.reason} | Rejected: {payload['reason']}"
    db.commit()
    background_tasks.add_task(notifications.send_refund_notice, refund.user_id, refund.id, refund.status)
    return {"status": "rejected"}


@router.post("/listings/{listing_id}/report", tags=["listings"])
def report_listing(listing_id: str, payload: dict[str, Any], current: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)):
    listing = db.get(models.Listing, listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail="listing not found")
    admins = db.query(models.User).filter(models.User.role == "admin", models.User.active.is_(True)).all()
    reason = str(payload.get("reason", "unspecified"))
    for admin in admins:
        db.add(models.Notification(user_id=admin.id, kind="listing_report", message=f"Listing {listing.id} reported by {current.id}: {reason}"))
    db.commit()
    return {"received": True, "listing_id": listing.id}
