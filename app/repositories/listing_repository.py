from __future__ import annotations

from datetime import datetime

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models import Book, Listing, User


class ListingRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def list_active_legacy_id_order(
        self,
        *,
        limit: int,
        after_listing_id: str | None,
    ) -> list[tuple[Listing, Book]]:
        query = (
            self._db.query(Listing, Book)
            .join(Book, Listing.book_id == Book.id)
            .filter(Listing.status == "active")
        )
        if after_listing_id is not None:
            query = query.filter(Listing.id > after_listing_id)
        return (
            query.order_by(Listing.id.asc())
            .limit(limit + 1)
            .all()
        )

    def list_active_v2_order(
        self,
        *,
        limit: int,
        before_created_at: datetime | None,
        before_listing_id: str | None,
    ) -> list[tuple[Listing, Book]]:
        query = (
            self._db.query(Listing, Book)
            .join(Book, Listing.book_id == Book.id)
            .filter(Listing.status == "active")
        )
        if before_created_at is not None and before_listing_id is not None:
            query = query.filter(
                or_(
                    Listing.created_at < before_created_at,
                    and_(
                        Listing.created_at == before_created_at,
                        Listing.id < before_listing_id,
                    ),
                )
            )
        return (
            query.order_by(Listing.created_at.desc(), Listing.id.desc())
            .limit(limit + 1)
            .all()
        )

    def get_with_book_and_seller(self, listing_id: str) -> tuple[Listing, Book, User] | None:
        row = (
            self._db.query(Listing, Book, User)
            .join(Book, Listing.book_id == Book.id)
            .join(User, Listing.seller_id == User.id)
            .filter(Listing.id == listing_id)
            .first()
        )
        if row is None:
            return None
        return row[0], row[1], row[2]

    def get_with_book(self, listing_id: str) -> tuple[Listing, Book] | None:
        row = (
            self._db.query(Listing, Book)
            .join(Book, Listing.book_id == Book.id)
            .filter(Listing.id == listing_id)
            .first()
        )
        if row is None:
            return None
        return row[0], row[1]
