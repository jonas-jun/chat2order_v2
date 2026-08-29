import streamlit as st
from pydantic import ValidationError

from core import cart as cart_fns
from core import db as dbfns
from core import pending as pending_fns
from core.access import get_db, require_staff
from core.models import CartItem, OrderDraft
from core.retry import call_with_retry
from core.session_keys import (
    ADDRESS_CANDIDATES,
    CART,
    CART_VERSION,
    EDITING_ORDER_ID,
    ORDER_FORM_VERSION,
    PENDING_ORDERS,
)
from core.settings import KST, get_env
from core.textutil import phone_digits as digits_of
from core.zipcode import search_addresses

db = get_db()
owner, staff_name = require_staff(db)

broadcast_id = st.query_params.get("b")
if not broadcast_id:
    st.error("방송이 지정되지 않은 링크입니다. 관리자에게 링크를 다시 확인하세요.")
    st.stop()

broadcast = dbfns.get_broadcast(db, broadcast_id)
if broadcast is None or broadcast.owner_user_id != owner:
    st.error("해당 방송을 찾을 수 없습니다. 관리자에게 링크를 다시 확인하세요.")
    st.stop()


@st.fragment(run_every="60s")
def render_header() -> None:
    count = len(dbfns.list_order_rows(db, broadcast.id, status="received"))
    status_label = "🟢 진행중" if broadcast.status == "open" else "🔴 마감"
    pending_count = len(st.session_state.get(PENDING_ORDERS, []))
    pending_label = f" · 🛒 미제출 {pending_count}건" if pending_count else ""
    st.markdown(
        f"#### 🎥 {broadcast.title} · "
        f"{broadcast.scheduled_at.astimezone(KST).strftime('%Y-%m-%d %H:%M')} · "
        f"{status_label} · 접수 {count}건{pending_label} · 👤 {staff_name}"
    )


render_header()

is_closed = broadcast.status != "open"
if is_closed:
    st.warning("이 방송은 마감되었습니다. 관리자가 재개하기 전까지 새 주문·수정을 받을 수 없습니다.")


@st.cache_data(ttl=300)
def _load_products(bid: str):
    return dbfns.list_products(db, bid)


products = _load_products(broadcast.id)
product_names = list(dict.fromkeys(p.product_name for p in products))

form_version = st.session_state.get(ORDER_FORM_VERSION, 0)
cart_version = st.session_state.get(CART_VERSION, 0)
editing_order_id = st.session_state.get(EDITING_ORDER_ID)
pending_orders = st.session_state.get(PENDING_ORDERS, [])


def _load_into_form(source, next_version: int) -> None:
    """주문(OrderRow) 또는 미제출 초안(OrderDraft)을 장바구니·고객정보 폼으로 되돌린다."""
    st.session_state[CART] = list(source.items)
    st.session_state[CART_VERSION] = cart_version + 1
    st.session_state[ORDER_FORM_VERSION] = next_version
    st.session_state[f"chat_name_{next_version}"] = source.chat_name or ""
    st.session_state[f"customer_name_{next_version}"] = source.customer_name
    st.session_state[f"phone_{next_version}"] = source.phone
    st.session_state[f"memo_{next_version}"] = source.memo or ""
    st.session_state[f"address_{next_version}"] = source.address
    st.session_state[f"address_detail_{next_version}"] = source.address_detail or ""
    st.session_state[f"zip_code_{next_version}"] = source.zip_code or ""


st.subheader("장바구니")
if not product_names:
    st.info("등록된 상품이 없습니다.")
else:
    pick_cols = st.columns([3, 3, 1, 1])
    selected_product = pick_cols[0].selectbox(
        "상품", product_names, key=f"pick_product_{form_version}", disabled=is_closed
    )
    matching = [p for p in products if p.product_name == selected_product]
    option_names = [p.option_name for p in matching]
    selected_option = pick_cols[1].selectbox(
        "옵션", option_names, key=f"pick_option_{form_version}", disabled=is_closed
    )
    quantity = pick_cols[2].number_input(
        "수량", min_value=1, value=1, step=1, key=f"pick_qty_{form_version}", disabled=is_closed
    )
    if pick_cols[3].button("담기", key=f"add_to_cart_{form_version}", disabled=is_closed):
        chosen = next(p for p in matching if p.option_name == selected_option)
        new_item = CartItem(
            product_id=chosen.id,
            product_name=chosen.product_name,
            option_name=chosen.option_name,
            unit_price=chosen.price,
            quantity=int(quantity),
        )
        st.session_state[CART] = cart_fns.add_item(st.session_state.get(CART, []), new_item)
        st.session_state[CART_VERSION] = cart_version + 1
        st.rerun()

cart = st.session_state.get(CART, [])
if cart:
    for idx, item in enumerate(cart):
        row = st.columns([3, 2, 1, 2, 1])
        row[0].write(item.product_name)
        row[1].write(item.option_name)
        new_qty = row[2].number_input(
            "수량",
            min_value=1,
            value=item.quantity,
            step=1,
            key=f"cart_qty_{idx}_{cart_version}",
            disabled=is_closed,
            label_visibility="collapsed",
        )
        if not is_closed and int(new_qty) != item.quantity:
            st.session_state[CART] = cart_fns.set_quantity(cart, idx, int(new_qty))
            st.session_state[CART_VERSION] = cart_version + 1
            st.rerun()
        row[3].write(f"{item.unit_price * item.quantity:,}원")
        if row[4].button("삭제", key=f"cart_del_{idx}_{cart_version}", disabled=is_closed):
            st.session_state[CART] = cart_fns.remove(cart, idx)
            st.session_state[CART_VERSION] = cart_version + 1
            st.rerun()
    st.markdown(f"**합계 {cart_fns.total(cart):,}원**")
else:
    st.caption("담긴 상품이 없습니다.")

st.divider()
st.subheader("고객 정보")

juso_key = get_env("JUSO_API_KEY")

info_col, address_col = st.columns(2)
with info_col:
    chat_name = st.text_input("채팅명", key=f"chat_name_{form_version}", disabled=is_closed)
    customer_name = st.text_input(
        "수령자명 *", key=f"customer_name_{form_version}", disabled=is_closed
    )
    phone = st.text_input("전화번호 *", key=f"phone_{form_version}", disabled=is_closed)
    memo = st.text_input("메모", key=f"memo_{form_version}", disabled=is_closed)

with address_col:
    search_cols = st.columns([3, 1])
    keyword = search_cols[0].text_input(
        "주소 검색",
        key=f"address_keyword_{form_version}",
        placeholder="예) 부산 북구 백양대로1050번길 16",
        disabled=is_closed,
    )
    if search_cols[1].button("검색", key=f"address_search_{form_version}", disabled=is_closed):
        candidates = search_addresses(keyword, juso_key)
        st.session_state[ADDRESS_CANDIDATES] = candidates
        if not candidates:
            st.warning("검색 결과가 없습니다. 직접 입력하거나 다른 키워드로 검색하세요.")

    candidates = st.session_state.get(ADDRESS_CANDIDATES, [])
    if candidates:
        options = {f"{c.road_addr} ({c.zip_code or '우편번호 미상'})": c for c in candidates}
        picked_label = st.radio(
            "검색 결과", list(options.keys()), key=f"address_candidates_{form_version}"
        )
        if st.button("이 주소 사용", key=f"use_address_{form_version}", disabled=is_closed):
            picked = options[picked_label]
            st.session_state[f"address_{form_version}"] = picked.road_addr
            st.session_state[f"zip_code_{form_version}"] = picked.zip_code or ""
            st.session_state[ADDRESS_CANDIDATES] = []
            st.rerun()

    address = st.text_input("주소 *", key=f"address_{form_version}", disabled=is_closed)
    address_detail = st.text_input("상세주소", key=f"address_detail_{form_version}", disabled=is_closed)
    zip_code = st.text_input("우편번호", key=f"zip_code_{form_version}", disabled=is_closed)

st.divider()

editing_order_id = st.session_state.get(EDITING_ORDER_ID)
phone_digits_value = digits_of(phone)
duplicate_orders = []
if phone_digits_value and not is_closed:
    duplicate_orders = [
        o
        for o in dbfns.find_orders_by_phone(db, broadcast.id, phone_digits_value)
        if o.id != editing_order_id
    ]
pending_dup_count = pending_fns.duplicate_phone_count(pending_orders, phone_digits_value)
total_dup_count = len(duplicate_orders) + pending_dup_count

confirm_duplicate = True
if total_dup_count:
    parts = []
    if duplicate_orders:
        parts.append(f"접수 {len(duplicate_orders)}건")
    if pending_dup_count:
        parts.append(f"미제출 {pending_dup_count}건")
    st.warning(f"같은 전화번호로 이미 {' · '.join(parts)} 있습니다.")
    confirm_duplicate = st.checkbox("그래도 진행", key=f"confirm_dup_{form_version}")


def _clear_form_after() -> None:
    st.session_state[CART] = []
    st.session_state.pop(EDITING_ORDER_ID, None)
    st.session_state[ADDRESS_CANDIDATES] = []
    st.session_state[ORDER_FORM_VERSION] = form_version + 1
    st.rerun()


action = None
if editing_order_id:
    if st.button(
        "💾 주문 수정 저장", key=f"save_order_{form_version}", type="primary", disabled=is_closed
    ):
        action = "update"
elif st.button(
    "🛒 주문 담기", key=f"save_order_{form_version}", type="primary", disabled=is_closed
):
    action = "queue"

if action:
    if total_dup_count and not confirm_duplicate:
        st.error("중복 경고를 확인하고 '그래도 진행'을 체크하세요.")
    else:
        try:
            draft = OrderDraft(
                staff_name=staff_name,
                customer_name=customer_name,
                phone=phone,
                address=address,
                address_detail=address_detail or None,
                zip_code=zip_code or None,
                chat_name=chat_name or None,
                memo=memo or None,
                items=cart,
            )
        except ValidationError as exc:
            for err in exc.errors():
                field = err["loc"][0] if err["loc"] else "입력값"
                st.error(f"{field}: {err['msg']}")
        else:
            if action == "update":
                try:
                    call_with_retry(lambda: dbfns.update_order(db, editing_order_id, draft))
                except Exception:
                    st.error("저장에 실패했습니다. 네트워크 문제일 수 있습니다. 다시 시도해 주세요.")
                else:
                    st.toast("주문을 수정했습니다.")
                    _clear_form_after()
            else:
                st.session_state[PENDING_ORDERS] = pending_fns.append(pending_orders, draft)
                st.toast("미제출 목록에 담았습니다.")
                _clear_form_after()

st.divider()
st.subheader(f"미제출 주문 ({len(pending_orders)}건)")
st.caption("제출 전까지 페이지를 새로고침하거나 닫으면 미제출 주문이 사라집니다.")

if not pending_orders:
    st.caption("담긴 미제출 주문이 없습니다.")
else:
    for idx, draft in enumerate(pending_orders):
        row = st.columns([3, 2, 4, 2, 1, 1])
        row[0].write(draft.customer_name)
        row[1].write(draft.phone)
        row[2].write(
            "; ".join(f"{i.product_name} {i.option_name} x{i.quantity}" for i in draft.items)
        )
        row[3].write(f"{sum(i.unit_price * i.quantity for i in draft.items):,}원")
        if row[4].button("수정", key=f"pending_edit_{idx}_{form_version}", disabled=is_closed):
            st.session_state[PENDING_ORDERS] = pending_fns.remove(pending_orders, idx)
            st.session_state.pop(EDITING_ORDER_ID, None)
            _load_into_form(draft, form_version + 1)
            st.session_state[ADDRESS_CANDIDATES] = []
            st.rerun()
        if row[5].button("삭제", key=f"pending_del_{idx}_{form_version}"):
            st.session_state[PENDING_ORDERS] = pending_fns.remove(pending_orders, idx)
            st.rerun()
    st.markdown(f"**미제출 합계 {pending_fns.total_amount(pending_orders):,}원**")
    if st.button(
        f"📤 전체 제출 ({len(pending_orders)}건)",
        key=f"submit_pending_{form_version}",
        type="primary",
    ):
        created, failed = [], []
        for draft in pending_orders:
            try:
                call_with_retry(lambda d=draft: dbfns.create_order(db, broadcast, d))
                created.append(draft)
            except Exception:
                failed.append(draft)
        st.session_state[PENDING_ORDERS] = failed
        if failed:
            st.error(
                f"{len(created)}건 제출 완료, {len(failed)}건 실패. 남은 주문을 다시 제출해 주세요."
            )
        else:
            st.toast(f"{len(created)}건을 제출했습니다.")
        st.rerun()

st.divider()
st.subheader("내 접수 (최근 50건)")
my_orders = dbfns.list_my_recent_orders(db, broadcast.id, staff_name, limit=50)

if not my_orders:
    st.caption("아직 접수한 주문이 없습니다.")
else:
    table_rows = [
        {
            "주문번호": o.order_number,
            "수령자": o.customer_name,
            "전화번호": o.phone,
            "상품": "; ".join(f"{i.product_name} {i.option_name} x{i.quantity}" for i in o.items),
            "상태": "취소됨" if o.status == "cancelled" else "접수",
            "접수시각": o.created_at_kst,
        }
        for o in my_orders
    ]
    selection = st.dataframe(
        table_rows,
        width="stretch",
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key=f"my_orders_table_{form_version}",
    )
    selected_rows = selection.selection.rows if selection and selection.selection else []
    if selected_rows:
        selected_order = my_orders[selected_rows[0]]
        if selected_order.status == "cancelled":
            st.caption("취소된 주문입니다.")
        else:
            action_cols = st.columns(2)
            if action_cols[0].button(
                "이 주문 수정하기", key=f"edit_{selected_order.id}", disabled=is_closed
            ):
                st.session_state[EDITING_ORDER_ID] = selected_order.id
                _load_into_form(selected_order, form_version + 1)
                st.rerun()

            confirm_cancel = action_cols[1].checkbox(
                "취소 확인", key=f"confirm_cancel_{selected_order.id}"
            )
            if action_cols[1].button(
                "이 주문 취소", disabled=is_closed or not confirm_cancel, key=f"cancel_{selected_order.id}"
            ):
                try:
                    call_with_retry(lambda: dbfns.cancel_order(db, selected_order.id))
                except Exception:
                    st.error("취소에 실패했습니다. 네트워크 문제일 수 있습니다. 다시 시도해 주세요.")
                else:
                    st.toast("주문을 취소했습니다.")
                    st.rerun()
