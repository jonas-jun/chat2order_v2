"""live_* 테이블 접근 함수.

RLS 를 쓰지 않으므로(서버가 서비스 키로 접근) 소유자 범위를 코드로 강제한다.
조회 함수는 모두 ``owner_user_id`` 또는 그로부터 확정된 ``broadcast_id`` 를
필수 인자로 받아 누락을 구조적으로 막는다.
"""

from __future__ import annotations

import math
import secrets
from datetime import datetime

from core.models import Broadcast, OrderDraft, OrderRow, Product, ProductInput
from core.settings import KST


def get_connection(url: str, key: str):
    from supabase import create_client

    return create_client(url, key)


def _clean(row: dict) -> dict:
    """pandas 를 거친 값의 NaN 을 None 으로 바꿔 insert 에 안전하게 만든다."""
    return {
        k: (None if isinstance(v, float) and math.isnan(v) else v) for k, v in row.items()
    }


def authenticate_admin(conn, user_id: str, password: str) -> bool:
    """v1 과 동일한 평문 비교. 바꾸면 v1 로그인이 깨지므로 해시 전환은 범위 밖."""
    response = (
        conn.table("accounts")
        .select("is_active")
        .eq("user_id", user_id)
        .eq("password", password)
        .execute()
    )
    return bool(response.data) and bool(response.data[0].get("is_active"))


def get_owner_by_staff_token(conn, token: str) -> str | None:
    if not token:
        return None
    response = (
        conn.table("accounts").select("user_id, is_active").eq("staff_token", token).execute()
    )
    if not response.data:
        return None
    account = response.data[0]
    return account["user_id"] if account.get("is_active") else None


def get_staff_token(conn, user_id: str) -> str | None:
    response = conn.table("accounts").select("staff_token").eq("user_id", user_id).execute()
    return response.data[0].get("staff_token") if response.data else None


def get_gemini_api_key(conn, user_id: str) -> str | None:
    response = conn.table("accounts").select("gemini_api_key").eq("user_id", user_id).execute()
    return response.data[0].get("gemini_api_key") if response.data else None


def rotate_staff_token(conn, user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    conn.table("accounts").update({"staff_token": token}).eq("user_id", user_id).execute()
    return token


def create_broadcast(
    conn,
    owner: str,
    title: str,
    scheduled_at: datetime,
    memo: str | None,
    products: list[ProductInput],
) -> str:
    broadcast_row = _clean(
        {
            "owner_user_id": owner,
            "title": title,
            "scheduled_at": scheduled_at.isoformat(),
            "memo": memo,
            "created_at": datetime.now(KST).isoformat(),
        }
    )
    broadcast_id = conn.table("live_broadcasts").insert(broadcast_row).execute().data[0]["id"]

    product_rows = _product_rows(broadcast_id, products)
    if product_rows:
        conn.table("live_products").insert(product_rows).execute()

    return broadcast_id


def _product_rows(broadcast_id: str, products: list[ProductInput]) -> list[dict]:
    return [
        _clean(
            {
                "broadcast_id": broadcast_id,
                "sort_order": idx,
                "product_name": p.product_name,
                "option_name": p.option_name,
                "price": p.price,
                "is_active": True,
            }
        )
        for idx, p in enumerate(products)
    ]


def list_broadcasts(conn, owner: str, limit: int = 20) -> list[Broadcast]:
    response = (
        conn.table("live_broadcasts")
        .select("*")
        .eq("owner_user_id", owner)
        .order("scheduled_at", desc=True)
        .limit(limit)
        .execute()
    )
    return [Broadcast(**row) for row in response.data]


def count_orders_by_broadcast(conn, broadcast_ids: list[str]) -> dict[str, int]:
    if not broadcast_ids:
        return {}
    response = (
        conn.table("live_orders")
        .select("broadcast_id")
        .in_("broadcast_id", broadcast_ids)
        .eq("status", "received")
        .execute()
    )
    counts = {bid: 0 for bid in broadcast_ids}
    for row in response.data:
        counts[row["broadcast_id"]] = counts.get(row["broadcast_id"], 0) + 1
    return counts


def get_broadcast(conn, broadcast_id: str) -> Broadcast | None:
    response = conn.table("live_broadcasts").select("*").eq("id", broadcast_id).execute()
    return Broadcast(**response.data[0]) if response.data else None


def set_broadcast_status(conn, broadcast_id: str, status: str) -> None:
    update = {"status": status}
    if status == "closed":
        update["closed_at"] = datetime.now(KST).isoformat()
    conn.table("live_broadcasts").update(update).eq("id", broadcast_id).execute()


# PostgREST 는 한 응답에 기본 1000행까지만 반환하므로, 상품이 1000개를 넘으면
# range 로 페이지를 이어 받아 전부 가져온다. (재고 카탈로그는 1000 옵션 초과 가능)
_PAGE_SIZE = 1000


def list_products(conn, broadcast_id: str, active_only: bool = True) -> list[Product]:
    rows: list[dict] = []
    start = 0
    while True:
        query = conn.table("live_products").select("*").eq("broadcast_id", broadcast_id)
        if active_only:
            query = query.eq("is_active", True)
        page = (
            query.order("sort_order", desc=False)
            .range(start, start + _PAGE_SIZE - 1)
            .execute()
            .data
        )
        rows.extend(page)
        if len(page) < _PAGE_SIZE:
            break
        start += _PAGE_SIZE
    return [Product(**row) for row in rows]


def replace_products(conn, broadcast_id: str, products: list[ProductInput]) -> None:
    """CSV 재업로드로 상품 전체를 교체한다. 주문이 1건이라도 있으면 거부한다."""
    existing = (
        conn.table("live_orders")
        .select("id", count="exact")
        .eq("broadcast_id", broadcast_id)
        .execute()
    )
    order_count = existing.count if existing.count is not None else len(existing.data)
    if order_count > 0:
        raise ValueError("주문이 있는 방송은 상품을 교체할 수 없습니다")

    conn.table("live_products").delete().eq("broadcast_id", broadcast_id).execute()
    rows = _product_rows(broadcast_id, products)
    if rows:
        conn.table("live_products").insert(rows).execute()


def _build_order_number(scheduled_at: datetime, seq: int) -> str:
    return scheduled_at.astimezone(KST).strftime("%Y%m%d") + f"{seq:03d}"


def create_order(conn, broadcast: Broadcast, draft: OrderDraft) -> OrderRow:
    seq = conn.rpc("live_next_order_seq", {"p_broadcast_id": broadcast.id}).execute().data
    order_number = _build_order_number(broadcast.scheduled_at, seq)

    order_row = _clean(
        {
            "broadcast_id": broadcast.id,
            "owner_user_id": broadcast.owner_user_id,
            "order_seq": seq,
            "order_number": order_number,
            "staff_name": draft.staff_name,
            "chat_name": draft.chat_name,
            "customer_name": draft.customer_name,
            "phone": draft.phone,
            "phone_digits": draft.phone_digits,
            "address": draft.address,
            "address_detail": draft.address_detail,
            "zip_code": draft.zip_code,
            "memo": draft.memo,
            "status": "received",
            "created_at": datetime.now(KST).isoformat(),
        }
    )
    order_id = conn.table("live_orders").insert(order_row).execute().data[0]["id"]

    try:
        _insert_items(conn, order_id, draft)
    except Exception:
        # supabase-py 는 트랜잭션이 없어 아이템 저장 실패 시 주문을 보상 삭제한다.
        conn.table("live_orders").delete().eq("id", order_id).execute()
        raise

    return _fetch_order_row(conn, order_id)


def _insert_items(conn, order_id: str, draft: OrderDraft) -> None:
    item_rows = [
        _clean(
            {
                "order_id": order_id,
                "product_id": item.product_id,
                "product_name": item.product_name,
                "option_name": item.option_name,
                "unit_price": item.unit_price,
                "quantity": item.quantity,
            }
        )
        for item in draft.items
    ]
    conn.table("live_order_items").insert(item_rows).execute()


def _fetch_order_row(conn, order_id: str) -> OrderRow:
    order = conn.table("live_orders").select("*").eq("id", order_id).execute().data[0]
    items = conn.table("live_order_items").select("*").eq("order_id", order_id).execute().data
    return OrderRow.from_order_and_items(order, items)


def update_order(conn, order_id: str, draft: OrderDraft) -> OrderRow:
    update = _clean(
        {
            "staff_name": draft.staff_name,
            "chat_name": draft.chat_name,
            "customer_name": draft.customer_name,
            "phone": draft.phone,
            "phone_digits": draft.phone_digits,
            "address": draft.address,
            "address_detail": draft.address_detail,
            "zip_code": draft.zip_code,
            "memo": draft.memo,
            "updated_at": datetime.now(KST).isoformat(),
        }
    )
    conn.table("live_orders").update(update).eq("id", order_id).execute()
    conn.table("live_order_items").delete().eq("order_id", order_id).execute()
    _insert_items(conn, order_id, draft)
    return _fetch_order_row(conn, order_id)


def cancel_order(conn, order_id: str) -> None:
    conn.table("live_orders").update(
        {"status": "cancelled", "updated_at": datetime.now(KST).isoformat()}
    ).eq("id", order_id).execute()


def update_order_zip(
    conn, order_id: str, zip_code: str | None, search_address: str | None = None
) -> None:
    update: dict = {"zip_code": zip_code}
    if search_address is not None:
        update["search_address"] = search_address
    conn.table("live_orders").update(update).eq("id", order_id).execute()


def list_my_recent_orders(
    conn, broadcast_id: str, staff_name: str, limit: int = 20
) -> list[OrderRow]:
    orders = (
        conn.table("live_orders")
        .select("*")
        .eq("broadcast_id", broadcast_id)
        .eq("staff_name", staff_name)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
        .data
    )
    return _attach_items(conn, orders)


def find_orders_by_phone(conn, broadcast_id: str, phone_digits: str) -> list[OrderRow]:
    orders = (
        conn.table("live_orders")
        .select("*")
        .eq("broadcast_id", broadcast_id)
        .eq("phone_digits", phone_digits)
        .eq("status", "received")
        .execute()
        .data
    )
    return _attach_items(conn, orders)


def search_orders(
    conn,
    owner: str,
    *,
    name: str | None = None,
    phone_digits: str | None = None,
    chat_name: str | None = None,
    broadcast_id: str | None = None,
    limit: int = 200,
) -> list[OrderRow]:
    query = conn.table("live_orders").select("*").eq("owner_user_id", owner)
    if broadcast_id:
        query = query.eq("broadcast_id", broadcast_id)
    if phone_digits:
        query = query.eq("phone_digits", phone_digits)
    if name:
        query = query.ilike("customer_name", f"%{name}%")
    if chat_name:
        query = query.ilike("chat_name", f"%{chat_name}%")
    orders = query.order("created_at", desc=True).limit(limit).execute().data
    return _attach_items(conn, orders)


def list_order_rows(conn, broadcast_id: str, status: str = "received") -> list[OrderRow]:
    orders = (
        conn.table("live_orders")
        .select("*")
        .eq("broadcast_id", broadcast_id)
        .eq("status", status)
        .order("created_at", desc=False)
        .execute()
        .data
    )
    return _attach_items(conn, orders)


def _attach_items(conn, orders: list[dict]) -> list[OrderRow]:
    if not orders:
        return []
    order_ids = [o["id"] for o in orders]
    items = conn.table("live_order_items").select("*").in_("order_id", order_ids).execute().data
    items_by_order: dict[str, list[dict]] = {}
    for item in items:
        items_by_order.setdefault(item["order_id"], []).append(item)
    return [
        OrderRow.from_order_and_items(order, items_by_order.get(order["id"], []))
        for order in orders
    ]
