from datetime import datetime

import pytest

from core import db
from core.models import CartItem, OrderDraft, ProductInput
from core.settings import KST
from tests.fakes import FakeSupabase, install_order_seq_rpc

OWNER = "seller@example.com"


@pytest.fixture
def fake():
    f = FakeSupabase()
    install_order_seq_rpc(f)
    return f


def _seed_broadcast(fake, scheduled_at=None):
    scheduled_at = scheduled_at or datetime(2026, 8, 30, 20, 0, tzinfo=KST)
    products = [
        ProductInput(product_name="가디건", option_name="그레이", price=78000),
        ProductInput(product_name="스커트", option_name="단일", price=129000),
    ]
    broadcast_id = db.create_broadcast(fake, OWNER, "8/30 라방", scheduled_at, None, products)
    return broadcast_id


def _draft(**overrides):
    base = dict(
        staff_name="민지",
        customer_name="홍길동",
        phone="01011112222",
        address="서울 강남구 테헤란로 1",
        items=[CartItem(product_name="가디건", option_name="그레이", unit_price=78000, quantity=1)],
    )
    base.update(overrides)
    return OrderDraft(**base)


def test_authenticate_admin_checks_password_and_active(fake):
    fake.tables.setdefault("accounts", []).append(
        {"user_id": OWNER, "password": "pw", "is_active": True}
    )
    assert db.authenticate_admin(fake, OWNER, "pw") is True
    assert db.authenticate_admin(fake, OWNER, "wrong") is False
    assert db.authenticate_admin(fake, "nobody@example.com", "pw") is False


def test_authenticate_admin_rejects_inactive_account(fake):
    fake.tables.setdefault("accounts", []).append(
        {"user_id": OWNER, "password": "pw", "is_active": False}
    )
    assert db.authenticate_admin(fake, OWNER, "pw") is False


def test_get_owner_by_staff_token(fake):
    fake.tables.setdefault("accounts", []).append(
        {"user_id": OWNER, "staff_token": "tok-1", "is_active": True}
    )
    assert db.get_owner_by_staff_token(fake, "tok-1") == OWNER
    assert db.get_owner_by_staff_token(fake, "missing") is None
    assert db.get_owner_by_staff_token(fake, "") is None


def test_rotate_staff_token_replaces_existing(fake):
    fake.tables.setdefault("accounts", []).append(
        {"user_id": OWNER, "staff_token": "old", "is_active": True}
    )
    new_token = db.rotate_staff_token(fake, OWNER)
    assert new_token != "old"
    assert db.get_owner_by_staff_token(fake, new_token) == OWNER
    assert db.get_owner_by_staff_token(fake, "old") is None


def test_create_broadcast_and_list_broadcasts(fake):
    broadcast_id = _seed_broadcast(fake)
    broadcasts = db.list_broadcasts(fake, OWNER)
    assert len(broadcasts) == 1
    assert broadcasts[0].id == broadcast_id
    assert broadcasts[0].title == "8/30 라방"

    products = db.list_products(fake, broadcast_id)
    assert [p.product_name for p in products] == ["가디건", "스커트"]


def test_list_products_returns_more_than_one_page(fake):
    # PostgREST 기본 1000행 상한을 넘겨도 range 페이지네이션으로 전부 받아야 한다.
    products = [
        ProductInput(product_name=f"상품{i:04d}", option_name="단일상품", price=1000)
        for i in range(1138)
    ]
    broadcast_id = db.create_broadcast(
        fake, OWNER, "대량 카탈로그", datetime(2026, 8, 30, 20, 0, tzinfo=KST), None, products
    )
    loaded = db.list_products(fake, broadcast_id)
    assert len(loaded) == 1138
    assert [p.sort_order for p in loaded] == list(range(1138))


def test_count_orders_by_broadcast(fake):
    broadcast_id = _seed_broadcast(fake)
    broadcast = db.get_broadcast(fake, broadcast_id)
    db.create_order(fake, broadcast, _draft())
    counts = db.count_orders_by_broadcast(fake, [broadcast_id])
    assert counts[broadcast_id] == 1


def test_order_queries_return_more_than_one_page(fake):
    # PostgREST 기본 1000행 상한을 넘는 주문·아이템도 전부 받아야 한다.
    # 각 주문에 아이템 2개 → 1200주문이면 아이템은 2400행(1000 초과).
    broadcast_id = _seed_broadcast(fake)
    broadcast = db.get_broadcast(fake, broadcast_id)
    for _ in range(1200):
        db.create_order(
            fake,
            broadcast,
            _draft(
                items=[
                    CartItem(product_name="가디건", option_name="그레이", unit_price=78000, quantity=1),
                    CartItem(product_name="스커트", option_name="단일", unit_price=129000, quantity=1),
                ]
            ),
        )

    rows = db.list_order_rows(fake, broadcast_id)
    assert len(rows) == 1200  # 주문 누락 없음
    assert all(len(r.items) == 2 for r in rows)  # 아이템 누락 없음

    counts = db.count_orders_by_broadcast(fake, [broadcast_id])
    assert counts[broadcast_id] == 1200  # 카운트 과소 집계 없음


def test_set_broadcast_status_closed_sets_closed_at(fake):
    broadcast_id = _seed_broadcast(fake)
    db.set_broadcast_status(fake, broadcast_id, "closed")
    broadcast = db.get_broadcast(fake, broadcast_id)
    assert broadcast.status == "closed"
    assert broadcast.closed_at is not None


def test_replace_products_blocked_when_orders_exist(fake):
    broadcast_id = _seed_broadcast(fake)
    broadcast = db.get_broadcast(fake, broadcast_id)
    db.create_order(fake, broadcast, _draft())

    with pytest.raises(ValueError):
        db.replace_products(fake, broadcast_id, [ProductInput(product_name="새상품", option_name="단일상품", price=1000)])


def test_replace_products_succeeds_without_orders(fake):
    broadcast_id = _seed_broadcast(fake)
    db.replace_products(
        fake, broadcast_id, [ProductInput(product_name="새상품", option_name="단일상품", price=1000)]
    )
    products = db.list_products(fake, broadcast_id)
    assert [p.product_name for p in products] == ["새상품"]


def test_create_order_assigns_sequential_order_numbers(fake):
    broadcast_id = _seed_broadcast(fake, scheduled_at=datetime(2026, 8, 30, 20, 0, tzinfo=KST))
    broadcast = db.get_broadcast(fake, broadcast_id)

    row1 = db.create_order(fake, broadcast, _draft(customer_name="고객1"))
    row2 = db.create_order(fake, broadcast, _draft(customer_name="고객2"))

    assert row1.order_number == "20260830001"
    assert row2.order_number == "20260830002"
    assert row1.items[0].product_name == "가디건"
    assert row1.full_address == "서울 강남구 테헤란로 1"


def test_create_order_compensates_when_item_insert_fails(fake):
    broadcast_id = _seed_broadcast(fake)
    broadcast = db.get_broadcast(fake, broadcast_id)

    fake.fail_next_insert("live_order_items", RuntimeError("boom"))
    with pytest.raises(RuntimeError):
        db.create_order(fake, broadcast, _draft())

    assert fake.tables["live_orders"] == []
    assert fake.tables.get("live_order_items", []) == []


def test_update_order_replaces_items(fake):
    broadcast_id = _seed_broadcast(fake)
    broadcast = db.get_broadcast(fake, broadcast_id)
    created = db.create_order(fake, broadcast, _draft())

    updated_draft = _draft(
        items=[CartItem(product_name="스커트", option_name="단일", unit_price=129000, quantity=2)]
    )
    updated = db.update_order(fake, created.id, updated_draft)

    assert len(updated.items) == 1
    assert updated.items[0].product_name == "스커트"
    assert updated.items[0].quantity == 2


def test_cancel_order_sets_status(fake):
    broadcast_id = _seed_broadcast(fake)
    broadcast = db.get_broadcast(fake, broadcast_id)
    created = db.create_order(fake, broadcast, _draft())

    db.cancel_order(fake, created.id)

    rows = db.list_order_rows(fake, broadcast_id, status="received")
    assert rows == []
    cancelled = [r for r in fake.tables["live_orders"] if r["id"] == created.id][0]
    assert cancelled["status"] == "cancelled"


def test_update_order_zip_stores_search_address(fake):
    broadcast_id = _seed_broadcast(fake)
    broadcast = db.get_broadcast(fake, broadcast_id)
    created = db.create_order(fake, broadcast, _draft())

    db.update_order_zip(fake, created.id, "12345", search_address="서울 강남구 테헤란로 1")

    stored = [r for r in fake.tables["live_orders"] if r["id"] == created.id][0]
    assert stored["zip_code"] == "12345"
    assert stored["search_address"] == "서울 강남구 테헤란로 1"


def test_list_my_recent_orders_filters_by_staff(fake):
    broadcast_id = _seed_broadcast(fake)
    broadcast = db.get_broadcast(fake, broadcast_id)
    db.create_order(fake, broadcast, _draft(staff_name="민지"))
    db.create_order(fake, broadcast, _draft(staff_name="유진"))

    rows = db.list_my_recent_orders(fake, broadcast_id, "민지")
    assert len(rows) == 1
    assert rows[0].staff_name == "민지"


def test_find_orders_by_phone_only_received(fake):
    broadcast_id = _seed_broadcast(fake)
    broadcast = db.get_broadcast(fake, broadcast_id)
    created = db.create_order(fake, broadcast, _draft(phone="01099998888"))

    found = db.find_orders_by_phone(fake, broadcast_id, "01099998888")
    assert len(found) == 1

    db.cancel_order(fake, created.id)
    assert db.find_orders_by_phone(fake, broadcast_id, "01099998888") == []


def test_search_orders_by_name_and_chat_name(fake):
    broadcast_id = _seed_broadcast(fake)
    broadcast = db.get_broadcast(fake, broadcast_id)
    db.create_order(fake, broadcast, _draft(customer_name="홍길동", chat_name="길동이"))
    db.create_order(fake, broadcast, _draft(customer_name="김철수", chat_name="철수짱"))

    by_name = db.search_orders(fake, OWNER, name="홍길동")
    assert len(by_name) == 1 and by_name[0].customer_name == "홍길동"

    by_chat = db.search_orders(fake, OWNER, chat_name="철수")
    assert len(by_chat) == 1 and by_chat[0].customer_name == "김철수"

    by_phone = db.search_orders(fake, OWNER, phone_digits="01011112222")
    assert len(by_phone) == 2


def test_list_order_rows_excludes_cancelled(fake):
    broadcast_id = _seed_broadcast(fake)
    broadcast = db.get_broadcast(fake, broadcast_id)
    keep = db.create_order(fake, broadcast, _draft(customer_name="유지"))
    cancelled = db.create_order(fake, broadcast, _draft(customer_name="취소"))
    db.cancel_order(fake, cancelled.id)

    rows = db.list_order_rows(fake, broadcast_id)
    assert [r.id for r in rows] == [keep.id]
