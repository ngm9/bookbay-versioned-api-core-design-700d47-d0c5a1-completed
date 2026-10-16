from app.models import Book, Listing, User


def legacy_all_listings_page(
    rows: list[tuple[Listing, Book]],
    *,
    limit: int,
    next_cursor: str | None,
) -> dict[str, object]:
    return {
        "data": [
            {
                "id": listing.id,
                "seller_id": listing.seller_id,
                "book": {"id": book.id, "title": book.title, "author": book.author},
                "price": str(listing.price),
                "condition": listing.condition,
            }
            for listing, book in rows
        ],
        "next_cursor": next_cursor,
    }


def legacy_get_listing_detail(listing: Listing, book: Book, seller: User) -> dict[str, object]:
    return {
        "listingId": listing.id,
        "sellerId": listing.seller_id,
        "sellerName": seller.display_name,
        "bookId": book.id,
        "title": book.title,
        "author": book.author,
        "isbn": book.isbn,
        "price": float(listing.price),
        "condition": listing.condition,
        "notes": listing.notes,
        "available": listing.quantity,
    }
