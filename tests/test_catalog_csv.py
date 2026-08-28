import io

import pytest

from core.catalog_csv import (
    parse_inventory_products,
    parse_price,
    parse_products_csv,
)


def _csv_bytes(text: str) -> io.BytesIO:
    return io.BytesIO(text.encode("utf-8-sig"))


@pytest.mark.parametrize(
    "text,expected",
    [
        ("78,000원", 78000),
        ("78000", 78000),
        (" 1,000 ", 1000),
        ("0", 0),
        (78000, 78000),
    ],
)
def test_parse_price_accepts_common_formats(text, expected):
    assert parse_price(text) == expected


@pytest.mark.parametrize("text", [None, "", "  ", "가격없음"])
def test_parse_price_rejects_invalid_values(text):
    with pytest.raises(ValueError):
        parse_price(text)


def test_parse_products_csv_happy_path():
    csv_text = "상품명,옵션내용,판매가\n가디건,그레이,78000\n스커트,단일,129000\n"
    products = parse_products_csv(_csv_bytes(csv_text))
    assert [(p.product_name, p.option_name, p.price) for p in products] == [
        ("가디건", "그레이", 78000),
        ("스커트", "단일", 129000),
    ]


def test_empty_option_defaults_to_danil_sangpum():
    csv_text = "상품명,옵션내용,판매가\n가디건,,78000\n"
    products = parse_products_csv(_csv_bytes(csv_text))
    assert products[0].option_name == "단일상품"


def test_blank_rows_are_skipped():
    csv_text = "상품명,옵션내용,판매가\n,,\n가디건,그레이,78000\n"
    products = parse_products_csv(_csv_bytes(csv_text))
    assert len(products) == 1


def test_duplicate_product_option_rows_keep_first_only():
    csv_text = "상품명,옵션내용,판매가\n가디건,그레이,78000\n가디건,그레이,99000\n"
    products = parse_products_csv(_csv_bytes(csv_text))
    assert len(products) == 1
    assert products[0].price == 78000


def test_missing_required_column_is_rejected():
    csv_text = "상품명,판매가\n가디건,78000\n"
    with pytest.raises(ValueError, match="컬럼이 필요합니다"):
        parse_products_csv(_csv_bytes(csv_text))


def test_invalid_price_error_includes_row_number():
    csv_text = "상품명,옵션내용,판매가\n가디건,그레이,78000\n스커트,단일,모름\n"
    with pytest.raises(ValueError, match="^3행:"):
        parse_products_csv(_csv_bytes(csv_text))


def test_cp949_encoded_csv_is_read():
    csv_text = "상품명,옵션내용,판매가\n가디건,그레이,78000\n"
    products = parse_products_csv(io.BytesIO(csv_text.encode("cp949")))
    assert products[0].product_name == "가디건"


# --- parse_inventory_products (재고 CSV: 상품명·옵션내용·판매단가) ---


def test_inventory_groups_options_by_product_and_attaches_price():
    csv_text = (
        "상품명,옵션내용,판매단가\n"
        "프리미엄H힐,블랙,79000\n"
        "프리미엄H힐,화이트,79000\n"
        "니트,그레이,55000\n"
    )
    products = parse_inventory_products(_csv_bytes(csv_text))
    assert [(p.product_name, p.option_name, p.price) for p in products] == [
        ("프리미엄H힐", "블랙", 79000),
        ("프리미엄H힐", "화이트", 79000),
        ("니트", "그레이", 55000),
    ]


def test_inventory_keeps_zero_price_options():
    csv_text = "상품명,옵션내용,판매단가\n멍참,그레이,10000\n멍참,블랙,0\n"
    products = parse_inventory_products(_csv_bytes(csv_text))
    assert [(p.option_name, p.price) for p in products] == [("그레이", 10000), ("블랙", 0)]


def test_inventory_blank_price_becomes_zero():
    csv_text = "상품명,옵션내용,판매단가\n니트,그레이,\n"
    products = parse_inventory_products(_csv_bytes(csv_text))
    assert products[0].price == 0


def test_inventory_dedups_options_within_product_keeping_first_price():
    csv_text = "상품명,옵션내용,판매단가\n니트,그레이,55000\n니트,그레이,99000\n"
    products = parse_inventory_products(_csv_bytes(csv_text))
    assert len(products) == 1
    assert products[0].price == 55000


def test_inventory_drops_blank_option_rows_and_products_without_options():
    csv_text = "상품명,옵션내용,판매단가\n니트,,55000\n,,\n힐,블랙,79000\n"
    products = parse_inventory_products(_csv_bytes(csv_text))
    assert [(p.product_name, p.option_name) for p in products] == [("힐", "블랙")]


def test_inventory_missing_column_is_rejected():
    csv_text = "상품명,옵션내용,판매가\n니트,그레이,55000\n"
    with pytest.raises(ValueError, match="판매단가"):
        parse_inventory_products(_csv_bytes(csv_text))
