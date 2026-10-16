from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import Book, Listing, User
from app.pagination_v2 import encode_listing_cursor
from app.services import ListingService


def _seed_listings(db_session: Session, seller: User) -> list[Listing]:
    book = Book(isbn="9780000000099", title="Physics", author="Newton", category="SCI")
    db_session.add(book)
    db_session.flush()
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    listings: list[Listing] = []
    for index in range(3):
        listing = Listing(
            book_id=book.id,
            seller_id=seller.id,
            price=Decimal(f"{10 + index}.00"),
            condition="good",
            quantity=1,
            status="active",
        )
        listing.created_at = base + timedelta(hours=index)
        listings.append(listing)
    db_session.add_all(listings)
    db_session.commit()
    for listing in listings:
        db_session.refresh(listing)
    return listings


def test_v2_listings_returns_canonical_shape(client, db_session, buyer):
    listings = _seed_listings(db_session, buyer)
    response = client.get("/v2/listings?limit=10")
    assert response.status_code == 200
    payload = response.json()
    assert "pagination" in payload
    assert payload["pagination"]["limit"] == 10
    assert len(payload["data"]) == 3
    first = payload["data"][0]
    assert first["id"] == listings[-1].id
    assert first["price"] == str(listings[-1].price)
    assert first["quantity_available"] == 1
    assert set(first.keys()) == {
        "id",
        "seller_id",
        "book_id",
        "title",
        "author",
        "price",
        "condition",
        "status",
        "quantity_available",
    }


def test_v2_listings_cursor_pagination(client, db_session, buyer):
    listings = _seed_listings(db_session, buyer)
    first_page = client.get("/v2/listings?limit=2")
    assert first_page.status_code == 200
    first_payload = first_page.json()
    assert len(first_payload["data"]) == 2
    assert first_payload["pagination"]["has_more"] is True
    assert first_payload["pagination"]["next_cursor"]

    second_page = client.get(f"/v2/listings?limit=2&cursor={first_payload['pagination']['next_cursor']}")
    second_payload = second_page.json()
    assert len(second_payload["data"]) == 1
    assert second_payload["pagination"]["has_more"] is False
    assert second_payload["data"][0]["id"] == listings[0].id


def test_v2_listings_invalid_cursor_problem_json(client, db_session, buyer):
    _seed_listings(db_session, buyer)
    response = client.get("/v2/listings?cursor=not-a-valid-cursor")
    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "invalid_cursor"


def test_v2_get_listing_success(client, db_session, buyer):
    listings = _seed_listings(db_session, buyer)
    response = client.get(f"/v2/listings/{listings[0].id}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == listings[0].id
    assert body["title"] == "Physics"


def test_v2_get_listing_not_found_problem_json(client):
    response = client.get("/v2/listings/does-not-exist")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "not_found"


def test_legacy_all_listings_contract_unchanged(client, db_session, buyer):
    listings = _seed_listings(db_session, buyer)
    response = client.get("/listings/all?limit=2")
    assert response.status_code == 200
    payload = response.json()
    assert "next_cursor" in payload
    assert "pagination" not in payload
    assert len(payload["data"]) == 2
    item = payload["data"][0]
    assert "book" in item
    assert "seller_id" in item
    assert item["id"] == sorted(listings, key=lambda row: row.id)[0].id


def test_legacy_get_listing_not_found_still_http_200(client):
    response = client.get("/listings/missing-listing")
    assert response.status_code == 200
    assert response.json() == {"error": "listing not found", "status": 404}


def test_listing_service_v2_ordering(db_session: Session, buyer: User):
    listings = _seed_listings(db_session, buyer)
    service = ListingService(db_session)
    page = service.list_active_v2(cursor=None, limit=10)
    assert [item.listing.id for item in page.items] == [listings[2].id, listings[1].id, listings[0].id]


def test_encode_decode_cursor_roundtrip():
    from app.pagination_v2 import decode_listing_cursor

    created_at = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
    cursor = encode_listing_cursor(created_at=created_at, listing_id="abc123")
    decoded_at, decoded_id = decode_listing_cursor(cursor)
    assert decoded_id == "abc123"
    assert decoded_at == created_at
