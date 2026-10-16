from fastapi import APIRouter, BackgroundTasks, Depends, Header, Query, Response
from sqlalchemy.orm import Session

from app import notifications, schemas_v2
from app.auth import AuthUser, get_current_user
from app.db import get_db
from app.problems import problem_response
from app.services import ListingService, ListingServiceError, OrderService, OrderServiceError

router = APIRouter(prefix="/v2", tags=["v2-partner"])


def _order_resource(result) -> schemas_v2.OrderResourceV2:
    order = result.order
    return schemas_v2.OrderResourceV2(
        id=order.id,
        cart_id=result.cart_id,
        cart_version=result.cart_version,
        status=order.status,
        total=order.total,
        created_at=order.created_at.isoformat(),
    )


@router.post("/orders", response_model=schemas_v2.OrderResourceV2, status_code=201)
def create_order_v2(
    payload: schemas_v2.OrderCreateV2,
    response: Response,
    background_tasks: BackgroundTasks,
    current: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    if not idempotency_key:
        return problem_response(
            status=400,
            code="idempotency_key_required",
            title="Missing Idempotency-Key",
            detail="Partner checkout requires an Idempotency-Key header",
            type_suffix="idempotency-key-required",
            instance="/v2/orders",
        )

    service = OrderService(db)
    try:
        result = service.create_from_cart(
            user_id=current.id,
            cart_id=payload.cart_id,
            address_id=payload.address_id,
            idempotency_key=idempotency_key,
        )
    except OrderServiceError as exc:
        status = exc.http_status
        return problem_response(
            status=status,
            code=exc.code,
            title="Checkout failed",
            detail=exc.message,
            type_suffix=exc.code.replace("_", "-"),
            instance="/v2/orders",
        )

    if not result.is_new:
        response.status_code = 200
    else:
        background_tasks.add_task(notifications.send_order_confirmation, current.id, result.order.id)

    return _order_resource(result)


def _listing_resource(view) -> schemas_v2.ListingResourceV2:
    payload = view.to_v2_resource()
    return schemas_v2.ListingResourceV2(**payload)


@router.get("/listings", response_model=schemas_v2.ListingListResponseV2)
def list_listings_v2(
    cursor: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    service = ListingService(db)
    try:
        page = service.list_active_v2(cursor=cursor, limit=limit)
    except ListingServiceError as exc:
        return problem_response(
            status=exc.http_status,
            code=exc.code,
            title="Listing collection failed",
            detail=exc.message,
            type_suffix=exc.code.replace("_", "-"),
            instance="/v2/listings",
        )

    return schemas_v2.ListingListResponseV2(
        data=[_listing_resource(item) for item in page.items],
        pagination=schemas_v2.PaginationMetaV2(
            limit=page.limit,
            next_cursor=page.next_cursor,
            has_more=page.has_more,
        ),
    )


@router.get("/listings/{listing_id}", response_model=schemas_v2.ListingResourceV2)
def get_listing_v2(listing_id: str, db: Session = Depends(get_db)):
    service = ListingService(db)
    try:
        view = service.get_v2(listing_id)
    except ListingServiceError as exc:
        return problem_response(
            status=exc.http_status,
            code=exc.code,
            title="Listing not found",
            detail=exc.message,
            type_suffix=exc.code.replace("_", "-"),
            instance=f"/v2/listings/{listing_id}",
        )
    return _listing_resource(view)
