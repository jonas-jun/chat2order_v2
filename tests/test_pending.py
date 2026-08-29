from core.models import CartItem, OrderDraft
from core.pending import append, duplicate_phone_count, remove, total_amount


def _draft(**overrides):
    base = dict(
        staff_name="민지",
        customer_name="홍길동",
        phone="010-1234-5678",
        address="부산 북구 백양대로1050번길 16",
        items=[CartItem(product_name="가디건", option_name="그레이", unit_price=1000, quantity=2)],
    )
    base.update(overrides)
    return OrderDraft(**base)


def test_append_adds_to_end_without_merging():
    pending = append([], _draft(customer_name="A"))
    pending = append(pending, _draft(customer_name="B"))
    assert [d.customer_name for d in pending] == ["A", "B"]


def test_append_does_not_mutate_input():
    original = [_draft(customer_name="A")]
    append(original, _draft(customer_name="B"))
    assert len(original) == 1


def test_remove_deletes_by_index():
    pending = [_draft(customer_name="A"), _draft(customer_name="B")]
    updated = remove(pending, 0)
    assert [d.customer_name for d in updated] == ["B"]
    assert len(pending) == 2


def test_total_amount_sums_all_drafts():
    pending = [
        _draft(items=[CartItem(product_name="p", option_name="o", unit_price=1000, quantity=2)]),
        _draft(items=[CartItem(product_name="q", option_name="o", unit_price=3000, quantity=1)]),
    ]
    assert total_amount(pending) == 5000


def test_total_amount_of_empty_queue_is_zero():
    assert total_amount([]) == 0


def test_duplicate_phone_count_matches_normalized_digits():
    pending = [_draft(phone="010-1234-5678"), _draft(phone="01099998888")]
    assert duplicate_phone_count(pending, "01012345678") == 1


def test_duplicate_phone_count_empty_phone_returns_zero():
    pending = [_draft(phone="010-1234-5678")]
    assert duplicate_phone_count(pending, "") == 0
