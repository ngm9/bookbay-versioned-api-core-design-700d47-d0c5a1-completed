from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class OrderCreateV2(BaseModel):
    cart_id: str = Field(min_length=1)
    address_id: str = Field(min_length=1)

    model_config = ConfigDict(str_strip_whitespace=True)


class OrderResourceV2(BaseModel):
    id: str
    cart_id: str
    cart_version: int
    status: str
    total: Decimal
    created_at: str

    model_config = ConfigDict(from_attributes=True)


class ListingResourceV2(BaseModel):
    id: str
    seller_id: str
    book_id: str
    title: str
    author: str
    price: str
    condition: str
    status: str
    quantity_available: int


class PaginationMetaV2(BaseModel):
    limit: int
    next_cursor: str | None
    has_more: bool


class ListingListResponseV2(BaseModel):
    data: list[ListingResourceV2]
    pagination: PaginationMetaV2
