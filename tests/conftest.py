import os
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import app.models  # noqa: F401,E402 — register all ORM tables on Base.metadata

from app.auth import AuthUser, get_current_user  # noqa: E402
from app.db import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Address, Book, Cart, CartItem, Listing, Order, User  # noqa: E402


@pytest.fixture()
def db_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def buyer(db_session: Session) -> User:
    user = User(email="buyer@example.com", display_name="Buyer", role="buyer")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture()
def checkout_ready(db_session: Session, buyer: User) -> dict[str, str]:
    book = Book(isbn="9780000000001", title="Algorithms", author="Author", category="CS")
    db_session.add(book)
    db_session.flush()

    listing = Listing(
        book_id=book.id,
        seller_id=buyer.id,
        price=Decimal("25.00"),
        condition="good",
        quantity=1,
    )
    address = Address(
        user_id=buyer.id,
        line1="100 Campus Dr",
        city="College Town",
        region="CA",
        postal_code="90001",
        country="US",
    )
    cart = Cart(user_id=buyer.id)
    db_session.add_all([listing, address, cart])
    db_session.flush()
    db_session.add(CartItem(cart_id=cart.id, listing_id=listing.id, quantity=1))
    db_session.commit()

    return {"cart_id": cart.id, "address_id": address.id}


@pytest.fixture()
def client(db_session: Session, buyer: User) -> TestClient:
    def override_db():
        try:
            yield db_session
        finally:
            pass

    def override_user() -> AuthUser:
        return AuthUser(id=buyer.id, email=buyer.email, role=buyer.role)

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
