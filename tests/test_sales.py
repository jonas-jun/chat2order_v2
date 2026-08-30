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


def test_normalize_ignores_case_and_spaces():
    assert sales.normalize(" 니트 가디건 ") == sales.normalize("니트가디건")
    assert sales.normalize("Wool Knit") == sales.normalize("woolknit")
    assert sales.normalize(None) == ""


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


def test_filter_by_keyword_matches_partial_product_name():
    rows = [_sold("니트 가디건", "그레이", 1), _sold("면 스커트", "단일", 2)]

    assert [r.product_name for r in sales.filter_by_keyword(rows, "가디")] == ["니트 가디건"]
    assert [r.product_name for r in sales.filter_by_keyword(rows, "니트가디건")] == ["니트 가디건"]
    assert sales.filter_by_keyword(rows, "없는상품") == []


def test_filter_by_keyword_returns_everything_when_blank():
    rows = [_sold("가디건", "그레이", 1), _sold("스커트", "단일", 2)]

    assert len(sales.filter_by_keyword(rows, "")) == 2
    assert len(sales.filter_by_keyword(rows, "   ")) == 2
    assert len(sales.filter_by_keyword(rows, None)) == 2


def test_group_by_product_preserves_order_and_totals_quantity():
    rows = [
        _sold("가디건", "그레이", 3),
        _sold("가디건", "블랙", 4),
        _sold("스커트", "단일", 2),
    ]
    groups = sales.group_by_product(rows)

    assert [g.product_name for g in groups] == ["가디건", "스커트"]
    assert groups[0].total_quantity == 7
    assert groups[1].total_quantity == 2


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
