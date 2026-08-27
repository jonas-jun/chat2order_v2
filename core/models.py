from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from core.settings import KST
from core.textutil import format_phone_number
from core.textutil import phone_digits as _phone_digits


class Broadcast(BaseModel):
    id: str
    owner_user_id: str
    title: str
    scheduled_at: datetime
    memo: str | None = None
    status: Literal["open", "closed"] = "open"
    last_order_seq: int = 0
    created_at: datetime | None = None
    closed_at: datetime | None = None


class Product(BaseModel):
    id: str
    broadcast_id: str
    sort_order: int
    product_name: str
    option_name: str
    price: int
    is_active: bool = True


class ProductInput(BaseModel):
    """상품 CSV 파싱 결과. DB 저장 시 목록 인덱스로 sort_order 를 부여한다."""

    product_name: str
    option_name: str
    price: int = Field(ge=0)


class CartItem(BaseModel):
    product_id: str | None = None
    product_name: str
    option_name: str
    unit_price: int
    quantity: int = Field(gt=0)


class OrderDraft(BaseModel):
    """직원이 입력한 주문 초안. 검증·정규화 후 ``db.create_order`` 로 저장된다."""

    staff_name: str
    customer_name: str
    phone: str
    address: str
    address_detail: str | None = None
    zip_code: str | None = None
    chat_name: str | None = None
    memo: str | None = None
    items: list[CartItem]
    phone_digits: str = ""

    @field_validator("staff_name", "customer_name", "address", mode="before")
    @classmethod
    def _reject_blank(cls, v: object) -> str:
        if v is None or not str(v).strip():
            raise ValueError("필수 항목입니다")
        return str(v).strip()

    @field_validator("phone", mode="before")
    @classmethod
    def _normalize_phone(cls, v: object) -> str:
        if v is None or not str(v).strip():
            raise ValueError("필수 항목입니다")
        formatted = format_phone_number(str(v).strip())
        return formatted or str(v).strip()

    @field_validator("items")
    @classmethod
    def _require_items(cls, v: list[CartItem]) -> list[CartItem]:
        if not v:
            raise ValueError("상품을 1개 이상 담아야 합니다")
        return v

    @model_validator(mode="after")
    def _merge_duplicate_items_and_derive_phone_digits(self) -> "OrderDraft":
        merged: dict[tuple[str | None, str, str], CartItem] = {}
        for item in self.items:
            key = (item.product_id, item.product_name, item.option_name)
            if key in merged:
                merged[key] = merged[key].model_copy(
                    update={"quantity": merged[key].quantity + item.quantity}
                )
            else:
                merged[key] = item
        self.items = list(merged.values())
        self.phone_digits = _phone_digits(self.phone)
        return self


class OrderRow(BaseModel):
    """검색·엑셀 출력을 위한 평탄화된 주문 행 (주문 + 아이템)."""

    id: str
    broadcast_id: str
    order_number: str
    staff_name: str
    chat_name: str | None = None
    customer_name: str
    phone: str
    address: str
    address_detail: str | None = None
    full_address: str
    zip_code: str | None = None
    search_address: str | None = None
    memo: str | None = None
    status: Literal["received", "cancelled"] = "received"
    created_at: datetime
    created_at_kst: str
    items: list[CartItem] = []

    @classmethod
    def from_order_and_items(cls, order: dict, items: list[dict]) -> "OrderRow":
        created_at = order["created_at"]
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)

        full_address = order["address"]
        if order.get("address_detail"):
            full_address = f"{full_address} {order['address_detail']}"

        return cls(
            id=order["id"],
            broadcast_id=order["broadcast_id"],
            order_number=order["order_number"],
            staff_name=order["staff_name"],
            chat_name=order.get("chat_name"),
            customer_name=order["customer_name"],
            phone=order["phone"],
            address=order["address"],
            address_detail=order.get("address_detail"),
            full_address=full_address,
            zip_code=order.get("zip_code"),
            search_address=order.get("search_address"),
            memo=order.get("memo"),
            status=order.get("status", "received"),
            created_at=created_at,
            created_at_kst=created_at.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S"),
            items=[
                CartItem(
                    product_id=i.get("product_id"),
                    product_name=i["product_name"],
                    option_name=i["option_name"],
                    unit_price=i["unit_price"],
                    quantity=i["quantity"],
                )
                for i in items
            ],
        )
