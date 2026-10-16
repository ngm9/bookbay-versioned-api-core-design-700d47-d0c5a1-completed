from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    display_name: str = Field(min_length=1, max_length=120)
    phone: str | None = Field(default=None, max_length=40)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.strip().lower()
        if "@" not in value:
            raise ValueError("invalid email")
        return value


class UserUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    phone: str | None = Field(default=None, max_length=40)


class AddressCreate(BaseModel):
    label: str = Field(default="Home", max_length=60)
    line1: str = Field(min_length=1, max_length=200)
    line2: str | None = Field(default=None, max_length=200)
    city: str = Field(min_length=1, max_length=100)
    region: str = Field(min_length=1, max_length=100)
    postal_code: str = Field(min_length=1, max_length=30)
    country: str = Field(default="US", min_length=2, max_length=2)

    model_config = ConfigDict(str_strip_whitespace=True)


class CartItemRequest(BaseModel):
    listing_id: str = Field(alias="listingId", min_length=1)
    quantity: int = Field(default=1, ge=1, le=20)

    model_config = ConfigDict(populate_by_name=True)


class OrderCreate(BaseModel):
    cart_id: str = Field(alias="cartId", min_length=1)
    address_id: str = Field(alias="addressId", min_length=1)

    model_config = ConfigDict(populate_by_name=True)


class PaymentRequest(BaseModel):
    provider: str = Field(min_length=1, max_length=40)
    payment_token: str = Field(alias="paymentToken", min_length=4, max_length=500)

    model_config = ConfigDict(populate_by_name=True)


class ListingCreate(BaseModel):
    book_id: str = Field(alias="bookId", min_length=1)
    price: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    condition: str = Field(min_length=2, max_length=40)
    notes: str | None = Field(default=None, max_length=2000)
    quantity: int = Field(default=1, ge=1, le=100)

    model_config = ConfigDict(populate_by_name=True)


class ListingUpdate(BaseModel):
    price: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    condition: str | None = Field(default=None, min_length=2, max_length=40)
    notes: str | None = Field(default=None, max_length=2000)
    quantity: int | None = Field(default=None, ge=0, le=100)
    status: str | None = Field(default=None, max_length=24)


class ReviewCreate(BaseModel):
    book_id: str = Field(alias="bookId", min_length=1)
    rating: int = Field(ge=1, le=5)
    body: str | None = Field(default=None, max_length=3000)

    model_config = ConfigDict(populate_by_name=True)
