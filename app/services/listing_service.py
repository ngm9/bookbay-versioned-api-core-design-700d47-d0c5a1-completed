from __future__ import annotations

import base64
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.legacy import listings as legacy_listings
from app.models import Book, Listing
from app.pagination_v2 import InvalidCursorError, decode_listing_cursor, encode_listing_cursor
from app.repositories.listing_repository import ListingRepository


class ListingServiceError(Exception):
    def __init__(self, code: str, message: str, http_status: int = 400) -> None:
        self.code = code
        self.message = message
        self.http_status = http_status
        super().__init__(message)


@dataclass(frozen=True)
class ListingView:
    listing: Listing
    book: Book

    def to_v2_resource(self) -> dict[str, object]:
        return {
            "id": self.listing.id,
            "seller_id": self.listing.seller_id,
            "book_id": self.book.id,
            "title": self.book.title,
            "author": self.book.author,
            "price": str(self.listing.price),
            "condition": self.listing.condition,
            "status": self.listing.status,
            "quantity_available": self.listing.quantity,
        }


@dataclass(frozen=True)
class V2ListingPage:
    items: list[ListingView]
    limit: int
    next_cursor: str | None
    has_more: bool


class ListingService:
    def __init__(self, db: Session) -> None:
        self._repo = ListingRepository(db)

    def list_active_legacy(self, *, cursor: str | None, limit: int) -> dict[str, object]:
        after_id: str | None = None
        if cursor:
            after_id = base64.urlsafe_b64decode(cursor.encode()).decode()

        rows = self._repo.list_active_legacy_id_order(limit=limit, after_listing_id=after_id)
        has_more = len(rows) > limit
        page_rows = rows[:limit]
        next_cursor = None
        if has_more and page_rows:
            next_cursor = base64.urlsafe_b64encode(page_rows[-1][0].id.encode()).decode()
        return legacy_listings.legacy_all_listings_page(page_rows, limit=limit, next_cursor=next_cursor)

    def list_active_v2(self, *, cursor: str | None, limit: int) -> V2ListingPage:
        before_created_at = None
        before_listing_id = None
        if cursor:
            try:
                before_created_at, before_listing_id = decode_listing_cursor(cursor)
            except InvalidCursorError as exc:
                raise ListingServiceError("invalid_cursor", str(exc), http_status=400) from exc

        rows = self._repo.list_active_v2_order(
            limit=limit,
            before_created_at=before_created_at,
            before_listing_id=before_listing_id,
        )
        has_more = len(rows) > limit
        page_rows = rows[:limit]
        views = [ListingView(listing=listing, book=book) for listing, book in page_rows]
        next_cursor = None
        if has_more and page_rows:
            last_listing, _ = page_rows[-1]
            next_cursor = encode_listing_cursor(created_at=last_listing.created_at, listing_id=last_listing.id)
        return V2ListingPage(items=views, limit=limit, next_cursor=next_cursor, has_more=has_more)

    def get_legacy_detail(self, listing_id: str) -> dict[str, object] | None:
        row = self._repo.get_with_book_and_seller(listing_id)
        if row is None:
            return None
        listing, book, seller = row
        return legacy_listings.legacy_get_listing_detail(listing, book, seller)

    def get_v2(self, listing_id: str) -> ListingView:
        row = self._repo.get_with_book(listing_id)
        if row is None:
            raise ListingServiceError("not_found", f"Listing {listing_id} was not found", http_status=404)
        listing, book = row
        return ListingView(listing=listing, book=book)
