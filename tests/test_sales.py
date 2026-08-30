from core import sales
from core.models import CartItem, OrderDraft, Product, ProductSalesRow


def _product(name, option, sort_order):
    return Product(
        id=f"p-{sort_order}",
        broadcast_id="b1",
        sort_order=sort_order,
        product_name=name,
        option_name=option,
        price=1000,
    )


def _sold(name, option, quantity, order_count=1):
    return ProductSalesRow(
        product_name=name, option_name=option, quantity=quantity, order_count=order_count
    )


def _draft(items):
    return OrderDraft(
        staff_name="민지",
        customer_name="홍길동",
        phone="01011112222",
        address="서울 강남구 테헤란로 1",
        items=items,
    )


def _item(name, option, quantity):
    return CartItem(product_name=name, option_name=option, unit_price=1000, quantity=quantity)


def test_merge_with_catalog_fills_unsold_options_with_zero():
    catalog = [_product("가디건", "그레이", 0), _product("가디건", "블랙", 1)]
    merged = sales.merge_with_catalog(catalog, [_sold("가디건", "블랙", 3, order_count=2)])

    assert [(r.option_name, r.quantity, r.order_count) for r in merged] == [
        ("그레이", 0, 0),
        ("블랙", 3, 2),
    ]


def test_merge_with_catalog_keeps_catalog_order():
    catalog = [
        _product("스커트", "단일", 0),
        _product("가디건", "그레이", 1),
    ]
    merged = sales.merge_with_catalog(catalog, [_sold("가디건", "그레이", 1)])

    assert [r.product_name for r in merged] == ["스커트", "가디건"]


def test_merge_with_catalog_appends_rows_missing_from_catalog():
    """카탈로그에서 사라진 상품이라도 주문 스냅샷에 있으면 누락시키지 않는다."""
    catalog = [_product("가디건", "그레이", 0)]
    merged = sales.merge_with_catalog(
        catalog, [_sold("가디건", "그레이", 1), _sold("지난방송상품", "단일", 5)]
    )

    assert [(r.product_name, r.quantity) for r in merged] == [
        ("가디건", 1),
        ("지난방송상품", 5),
    ]


def test_product_names_dedupes_and_keeps_order():
    rows = [
        _sold("가디건", "그레이", 1),
        _sold("가디건", "블랙", 2),
        _sold("스커트", "단일", 3),
    ]

    assert sales.product_names(rows) == ["가디건", "스커트"]


def test_product_names_empty():
    assert sales.product_names([]) == []


def test_group_for_collects_options_and_totals_quantity():
    rows = [
        _sold("가디건", "그레이", 3),
        _sold("스커트", "단일", 2),
        _sold("가디건", "블랙", 4),
    ]
    group = sales.group_for(rows, "가디건")

    assert [r.option_name for r in group.rows] == ["그레이", "블랙"]
    assert group.total_quantity == 7


def test_group_for_returns_none_for_unknown_product():
    assert sales.group_for([_sold("가디건", "그레이", 1)], "없는상품") is None


def test_pending_quantities_sums_across_drafts():
    pending = [
        _draft([_item("가디건", "그레이", 1), _item("스커트", "단일", 2)]),
        _draft([_item("가디건", "그레이", 3)]),
    ]

    assert sales.pending_quantities(pending) == {
        ("가디건", "그레이"): 4,
        ("스커트", "단일"): 2,
    }


def test_pending_quantities_empty_queue():
    assert sales.pending_quantities([]) == {}
