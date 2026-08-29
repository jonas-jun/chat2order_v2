from datetime import datetime, time

import streamlit as st

from core import db as dbfns
from core.access import get_db, logout, require_admin
from core.catalog_csv import parse_products_csv
from core.config import load_config
from core.export import build_excel, rows_to_frame
from core.links import public_url
from core.llm import load_prompt_template
from core.models import ProductInput
from core.session_keys import (
    CSV_UPLOADER_VERSION,
    GEMINI_API_KEY,
    NEW_BROADCAST_PRODUCTS,
    SELECTED_BROADCAST_ID,
)
from core.settings import KST, get_env
from core.zipcode import fill_zip_codes

db = get_db()
user_id = require_admin(db)

st.markdown(
    "## 📦 <span style='color:#FF6B35;font-weight:bold;'>C</span>hat"
    "<span style='color:#FF6B35;font-weight:bold;'>2O</span>rder Live",
    unsafe_allow_html=True,
)


def _public_url(path: str) -> str:
    # LIVE_PUBLIC_URL 이 없으면 현재 접속 주소의 origin 을 붙여 full URL 로 보여준다.
    try:
        current_url = st.context.url
    except Exception:
        current_url = None
    return public_url(path, get_env("LIVE_PUBLIC_URL"), current_url)


with st.sidebar:
    st.write(f"👤 {user_id}")
    if st.button("로그아웃", width="stretch"):
        logout()
        st.rerun()

    st.divider()
    sidebar_token = dbfns.get_staff_token(db, user_id)
    if sidebar_token:
        st.caption("주문 검색 (방송과 무관, 토큰당 고정)")
        st.markdown(f"[🔎 주문 검색 열기]({_public_url(f'/search?t={sidebar_token}')})")

    st.caption("링크가 유출된 경우에만 재발급하세요. 기존 링크가 즉시 무효화됩니다.")
    confirm_rotate = st.checkbox("정말 재발급합니다")
    if st.button("🔑 직원 토큰 재발급", disabled=not confirm_rotate, width="stretch"):
        new_token = dbfns.rotate_staff_token(db, user_id)
        st.session_state["_just_rotated_token"] = new_token
        st.rerun()

if "_just_rotated_token" in st.session_state:
    st.success(
        f"새 토큰이 발급되었습니다 (기존 링크는 무효화됨): `{st.session_state.pop('_just_rotated_token')}`"
    )

st.subheader("방송 목록")
broadcasts = dbfns.list_broadcasts(db, user_id)
counts = dbfns.count_orders_by_broadcast(db, [b.id for b in broadcasts])

if not broadcasts:
    st.info("아직 만든 방송이 없습니다. 아래에서 새 방송을 만드세요.")
else:
    header = st.columns([3, 2, 1, 1, 1])
    for col, label in zip(header, ["제목", "일시", "상태", "접수", ""]):
        col.markdown(f"**{label}**")
    for b in broadcasts:
        cols = st.columns([3, 2, 1, 1, 1])
        cols[0].write(b.title)
        cols[1].write(b.scheduled_at.astimezone(KST).strftime("%Y-%m-%d %H:%M"))
        cols[2].write("🟢 진행중" if b.status == "open" else "🔴 마감")
        cols[3].write(f"{counts.get(b.id, 0)}건")
        if cols[4].button("선택", key=f"select_{b.id}"):
            st.session_state[SELECTED_BROADCAST_ID] = b.id
            st.rerun()

st.divider()

selected_id = st.session_state.get(SELECTED_BROADCAST_ID)
if selected_id:
    broadcast = dbfns.get_broadcast(db, selected_id)
    if broadcast is None or broadcast.owner_user_id != user_id:
        st.session_state.pop(SELECTED_BROADCAST_ID, None)
        st.rerun()
    else:
        st.subheader(f"방송: {broadcast.title}")

        token = dbfns.get_staff_token(db, user_id)
        if token:
            st.code(_public_url(f"/order?b={broadcast.id}&t={token}"), language=None)
        else:
            st.warning("아직 직원 토큰이 없습니다. 사이드바에서 먼저 발급하세요.")

        action_cols = st.columns(2)
        if broadcast.status == "open":
            if action_cols[0].button("🔒 마감"):
                dbfns.set_broadcast_status(db, broadcast.id, "closed")
                st.rerun()
        else:
            if action_cols[0].button("▶️ 재개"):
                dbfns.set_broadcast_status(db, broadcast.id, "open")
                st.rerun()

        order_count = counts.get(broadcast.id, 0)

        with st.expander("📮 엑셀 다운로드 (우편번호 자동 보완)"):
            if order_count == 0:
                st.info("접수된 주문이 없습니다.")
            else:
                config = load_config()
                st.caption("주소는 있는데 우편번호가 비어있는 주문만 자동으로 한 번 조회합니다.")
                if st.button("엑셀 만들기", key=f"run_export_{broadcast.id}"):
                    order_rows = dbfns.list_order_rows(db, broadcast.id, status="received")
                    targets = [o for o in order_rows if o.address and not o.zip_code]

                    if targets:
                        gemini_key = st.session_state.get(GEMINI_API_KEY) or ""
                        if not gemini_key:
                            st.warning(
                                "Gemini API 키가 없어 LLM 정제를 생략합니다. JUSO 직접 조회만 시도합니다."
                            )
                        prompt_template = load_prompt_template(config["prompts"]["address_to_search"])
                        progress_bar = st.progress(0.0)
                        status_box = st.status("우편번호 조회 중입니다", expanded=True)
                        counts_by_stage = {"direct": 0, "refined": 0, "failed": 0}

                        results = fill_zip_codes(
                            targets,
                            juso_api_key=get_env("JUSO_API_KEY"),
                            gemini_api_key=gemini_key,
                            model=config["gemini"]["model"],
                            temperature=config["gemini"]["temperature"],
                            prompt_template=prompt_template,
                            progress_cb=lambda done, total: progress_bar.progress(min(done / total, 1.0)),
                        )
                        for order in targets:
                            result = results[order.id]
                            dbfns.update_order_zip(db, order.id, result.zip_code, result.search_address)
                            counts_by_stage[result.stage] += 1
                            order.zip_code = result.zip_code or order.zip_code
                            order.search_address = result.search_address or order.search_address

                        status_box.update(
                            label=(
                                f"🎉 우편번호 조회 완료! (직접 {counts_by_stage['direct']}건 · "
                                f"정제 {counts_by_stage['refined']}건 · 실패 {counts_by_stage['failed']}건)"
                            ),
                            state="complete",
                        )
                        metric_cols = st.columns(3)
                        metric_cols[0].metric("직접 조회 성공", counts_by_stage["direct"])
                        metric_cols[1].metric("LLM 정제 후 성공", counts_by_stage["refined"])
                        metric_cols[2].metric("실패", counts_by_stage["failed"])

                    live_output = config["live_output"]
                    frame = rows_to_frame(order_rows, config["live_output_columns"], live_output["row_mode"])
                    review_orders = [o for o in order_rows if not o.zip_code]
                    review_frame = (
                        rows_to_frame(
                            review_orders,
                            {
                                "주문번호": "order_number",
                                "수령자": "customer_name",
                                "전화번호": "phone",
                                "주소": "full_address",
                                "접수직원": "staff_name",
                            },
                            "order",
                        )
                        if review_orders
                        else None
                    )
                    excel_bytes = build_excel(
                        frame, review_frame, live_output["sheet_name"], live_output["review_sheet_name"]
                    )
                    file_name = live_output["file_name"].format(title=broadcast.title)
                    st.download_button(
                        "⬇️ 엑셀 다운로드",
                        data=excel_bytes,
                        file_name=file_name,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key=f"download_excel_{broadcast.id}",
                    )
        with st.expander("상품 CSV 교체 (주문이 없을 때만 가능)"):
            if order_count > 0:
                st.info("이미 접수된 주문이 있어 상품을 교체할 수 없습니다.")
            else:
                replace_file = st.file_uploader(
                    "새 상품 CSV", type="csv", key=f"replace_csv_{broadcast.id}"
                )
                if replace_file is not None:
                    try:
                        new_products = parse_products_csv(replace_file)
                    except ValueError as exc:
                        st.error(str(exc))
                    else:
                        st.dataframe([p.model_dump() for p in new_products], width="stretch")
                        if st.button("이 상품으로 교체", type="primary"):
                            try:
                                dbfns.replace_products(db, broadcast.id, new_products)
                            except ValueError as exc:
                                st.error(str(exc))
                            else:
                                st.success("상품을 교체했습니다.")
                                st.rerun()

    st.divider()

st.subheader("➕ 새 방송 만들기")

uploader_version = st.session_state.setdefault(CSV_UPLOADER_VERSION, 0)

with st.form("new_broadcast_form"):
    date_col, time_col = st.columns(2)
    scheduled_date = date_col.date_input("방송 일시 (날짜)")
    scheduled_time = time_col.time_input("방송 일시 (시각)", value=time(20, 0))
    st.caption("라방 ID 는 일정으로 자동 생성됩니다 (예: 20260829-2000).")
    memo = st.text_area("메모 (선택)")
    uploaded = st.file_uploader(
        "상품 CSV (재고 파일 stk_forInOut_*.csv 또는 상품명·옵션내용·판매가)",
        type="csv",
        key=f"new_csv_{uploader_version}",
    )
    submitted = st.form_submit_button("미리보기", type="primary")

if submitted:
    if uploaded is None:
        st.error("상품 CSV 를 업로드하세요.")
    else:
        try:
            products = parse_products_csv(uploaded)
        except ValueError as exc:
            st.error(str(exc))
        else:
            if not products:
                st.error("등록할 상품이 없습니다. CSV 내용을 확인하세요.")
            else:
                scheduled_at = datetime.combine(scheduled_date, scheduled_time, tzinfo=KST)
                st.session_state[NEW_BROADCAST_PRODUCTS] = {
                    "scheduled_at": scheduled_at.isoformat(),
                    "memo": memo.strip() or None,
                    "products": [p.model_dump() for p in products],
                }

preview = st.session_state.get(NEW_BROADCAST_PRODUCTS)
if preview:
    products_preview = preview["products"]
    prices = [p["price"] for p in products_preview]
    product_count = len({p["product_name"] for p in products_preview})
    option_count = len(products_preview)
    st.write(
        f"상품 {product_count}종 · 옵션 {option_count}개 · "
        f"가격 {min(prices):,}원~{max(prices):,}원"
    )
    st.dataframe(products_preview[:20], width="stretch")

    if st.button("✅ 저장하고 링크 발급", type="primary"):
        broadcast_id = dbfns.create_broadcast(
            db,
            user_id,
            datetime.fromisoformat(preview["scheduled_at"]),
            preview["memo"],
            [ProductInput(**p) for p in products_preview],
        )
        st.session_state.pop(NEW_BROADCAST_PRODUCTS, None)
        st.session_state[CSV_UPLOADER_VERSION] = uploader_version + 1
        st.session_state[SELECTED_BROADCAST_ID] = broadcast_id
        st.success("방송을 만들었습니다.")
        st.rerun()
