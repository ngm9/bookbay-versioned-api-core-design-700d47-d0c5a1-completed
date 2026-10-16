from sqlalchemy.orm import Session

from app.models import Address, Order


def test_legacy_create_order_success(client, checkout_ready):
    body = {"cartId": checkout_ready["cart_id"], "addressId": checkout_ready["address_id"]}
    response = client.post("/createOrder", json=body)
    assert response.status_code == 200
    payload = response.json()
    assert payload["cartId"] == checkout_ready["cart_id"]
    assert payload["status"] == "created"
    assert "orderId" in payload


def test_legacy_duplicate_checkout_returns_same_order(client, db_session: Session, checkout_ready):
    body = {"cartId": checkout_ready["cart_id"], "addressId": checkout_ready["address_id"]}
    first = client.post("/createOrder", json=body)
    second = client.post("/createOrder", json=body)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["orderId"] == second.json()["orderId"]
    assert db_session.query(Order).count() == 1


def test_idempotency_key_replay(client, db_session: Session, checkout_ready):
    body = {"cartId": checkout_ready["cart_id"], "addressId": checkout_ready["address_id"]}
    headers = {"Idempotency-Key": "checkout-key-1"}

    first = client.post("/createOrder", json=body, headers=headers)
    second = client.post("/createOrder", json=body, headers=headers)

    assert first.json()["orderId"] == second.json()["orderId"]
    assert db_session.query(Order).count() == 1


def test_idempotency_key_mismatch_returns_bad_request(client, db_session, checkout_ready, buyer):
    second_address = Address(
        user_id=buyer.id,
        line1="200 Campus Dr",
        city="College Town",
        region="CA",
        postal_code="90002",
        country="US",
    )
    db_session.add(second_address)
    db_session.commit()

    body = {"cartId": checkout_ready["cart_id"], "addressId": checkout_ready["address_id"]}
    client.post("/createOrder", json=body, headers={"Idempotency-Key": "key-a"})

    response = client.post(
        "/createOrder",
        json={"cartId": checkout_ready["cart_id"], "addressId": second_address.id},
        headers={"Idempotency-Key": "key-a"},
    )
    assert response.status_code == 400
    assert response.json()["error"] == "idempotency_key_mismatch"


def test_v2_requires_idempotency_key(client, checkout_ready):
    response = client.post(
        "/v2/orders",
        json={"cart_id": checkout_ready["cart_id"], "address_id": checkout_ready["address_id"]},
    )
    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "idempotency_key_required"


def test_v2_create_order_and_replay(client, db_session: Session, checkout_ready):
    body = {"cart_id": checkout_ready["cart_id"], "address_id": checkout_ready["address_id"]}
    headers = {"Idempotency-Key": "partner-key-1"}

    created = client.post("/v2/orders", json=body, headers=headers)
    replay = client.post("/v2/orders", json=body, headers=headers)

    assert created.status_code == 201
    assert replay.status_code == 200
    assert created.json()["id"] == replay.json()["id"]
    assert db_session.query(Order).count() == 1


def test_v2_idempotency_key_mismatch_is_problem_json(client, checkout_ready):
    body = {"cart_id": checkout_ready["cart_id"], "address_id": checkout_ready["address_id"]}
    client.post("/v2/orders", json=body, headers={"Idempotency-Key": "partner-mismatch"})

    response = client.post(
        "/v2/orders",
        json={"cart_id": checkout_ready["cart_id"], "address_id": "nonexistent-address"},
        headers={"Idempotency-Key": "partner-mismatch"},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "idempotency_key_mismatch"
