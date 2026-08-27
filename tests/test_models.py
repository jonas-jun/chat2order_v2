import pytest
from pydantic import ValidationError

from core.models import CartItem, OrderDraft


def _draft(**overrides):
    base = dict(
        staff_name="민지",
        customer_name="홍길동",
        phone="01012345678",
        address="서울 강남구 테헤란로 1",
        items=[CartItem(product_name="가디건", option_name="그레이", unit_price=1000, quantity=1)],
    )
    base.update(overrides)
    return OrderDraft(**base)


def test_phone_is_normalized_to_dashed_format():
    draft = _draft(phone="01012345678")
    assert draft.phone == "010-1234-5678"
    assert draft.phone_digits == "01012345678"


@pytest.mark.parametrize("field", ["staff_name", "customer_name", "address"])
def test_blank_required_fields_are_rejected(field):
    with pytest.raises(ValidationError):
        _draft(**{field: "   "})


def test_phone_is_required():
    with pytest.raises(ValidationError):
        _draft(phone="")


def test_items_must_not_be_empty():
    with pytest.raises(ValidationError):
        _draft(items=[])


def test_duplicate_product_and_option_items_are_merged():
    draft = _draft(
        items=[
            CartItem(product_id="p1", product_name="가디건", option_name="그레이", unit_price=1000, quantity=1),
            CartItem(product_id="p1", product_name="가디건", option_name="그레이", unit_price=1000, quantity=2),
            CartItem(product_id="p2", product_name="스커트", option_name="단일상품", unit_price=2000, quantity=1),
        ]
    )
    assert len(draft.items) == 2
    merged = next(i for i in draft.items if i.product_id == "p1")
    assert merged.quantity == 3


def test_quantity_must_be_positive():
    with pytest.raises(ValidationError):
        CartItem(product_name="가디건", option_name="그레이", unit_price=1000, quantity=0)
