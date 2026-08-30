"""상품별 주문 수량 패널. 주문 입력 화면과 관리자 화면이 함께 쓴다.

``core/access.py`` 와 같은 예외로 Streamlit 위젯을 직접 그린다 — 두 페이지에
같은 표를 붙여야 해서 렌더까지 한곳에 모으는 편이 중복보다 낫다. 집계 규칙은
``core/sales.py`` 에 순수 함수로 두고 여기서는 배치와 표시만 한다.

패널 전체를 fragment 로 감싼다. 상품 선택·새로고침이 페이지 전체를 rerun 하지 않아
주문 입력 폼이 흔들리지 않고, expander 도 열린 채로 남는다.
"""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from core import db as dbfns
from core import sales as sales_fns
from core.models import OrderDraft, Product, ProductSalesGroup, ProductSalesRow
from core.settings import KST

# 라방 중에는 수량이 계속 바뀌므로 짧게 잡는다. 캐시는 프로세스 단위라 같은
# 방송을 보는 직원 여러 명이 한 번의 조회를 나눠 쓴다.
_SALES_TTL_SECONDS = 20
# 카탈로그는 방송 중 바뀌지 않는다 (주문이 있으면 상품 교체가 막혀 있다).
_CATALOG_TTL_SECONDS = 300


@st.cache_data(ttl=_SALES_TTL_SECONDS, show_spinner=False)
def _load_sales(_db, broadcast_id: str) -> list[ProductSalesRow]:
    # 앞의 밑줄은 "이 인자는 캐시 키에서 빼라" 는 Streamlit 규약이다. Supabase
    # 클라이언트는 해시할 수 없고, 어차피 프로세스당 하나뿐이라 키에 넣을 이유도 없다.
    return dbfns.aggregate_product_sales(_db, broadcast_id)


@st.cache_data(ttl=_CATALOG_TTL_SECONDS, show_spinner=False)
def _load_catalog(_db, broadcast_id: str) -> list[Product]:
    return dbfns.list_products(_db, broadcast_id)


def render_sales_panel(
    db,
    broadcast_id: str,
    *,
    key_prefix: str,
    pending_orders: list[OrderDraft] | None = None,
) -> None:
    """접힌 expander 로 상품별 주문 수량 패널을 그린다.

    ``key_prefix`` 는 위젯 키 충돌을 막는 접두사다 (한 페이지에 패널이 하나뿐이라도
    페이지마다 다른 값을 준다). ``pending_orders`` 를 주면 그 세션의 미제출 수량을
    별도 컬럼으로 함께 보여준다.
    """
    with st.expander("📊 상품별 주문 수량"):
        _render_body(db, broadcast_id, key_prefix, pending_orders or [])


@st.fragment
def _render_body(
    db, broadcast_id: str, key_prefix: str, pending_orders: list[OrderDraft]
) -> None:
    sales = _load_sales(db, broadcast_id)
    catalog = _load_catalog(db, broadcast_id)
    rows = sales_fns.merge_with_catalog(catalog, sales)

    if not rows:
        st.caption("등록된 상품이 없습니다.")
        return

    pick_col, refresh_col = st.columns([4, 1], vertical_alignment="bottom")
    # selectbox 는 타이핑하면 목록을 걸러 준다. 상품이 수백 종이어도 이름 일부만
    # 치면 찾히므로 별도 검색창이 필요 없고, 고른 상품 하나만 표로 그린다.
    selected = pick_col.selectbox(
        "상품",
        sales_fns.product_names(rows),
        index=None,
        placeholder="상품명을 입력해 검색하세요",
        key=f"{key_prefix}_sales_product",
    )
    if refresh_col.button("🔄 새로고침", key=f"{key_prefix}_sales_refresh", width="stretch"):
        _load_sales.clear()

    group = sales_fns.group_for(rows, selected) if selected else None
    if group is None:
        st.caption("상품을 고르면 옵션별 주문 수량이 보입니다.")
        return

    st.markdown(f"**{group.product_name}** · 합계 {group.total_quantity:,}개")
    st.dataframe(
        _table_rows(group, sales_fns.pending_quantities(pending_orders)),
        width="stretch",
        hide_index=True,
    )
    st.caption(
        f"취소된 주문은 제외됩니다 · {datetime.now(KST).strftime('%H:%M:%S')} 기준"
    )


def _table_rows(group: ProductSalesGroup, pending_by_key: dict[tuple[str, str], int]) -> list[dict]:
    table: list[dict] = []
    for row in group.rows:
        entry = {
            "옵션": row.option_name,
            "주문수량": row.quantity,
            "주문건수": row.order_count,
        }
        if pending_by_key:
            entry["내 미제출"] = pending_by_key.get((row.product_name, row.option_name), 0)
        table.append(entry)
    return table
