import streamlit as st

from core import db as dbfns
from core.access import get_db, require_staff
from core.config import load_config
from core.export import build_excel, rows_to_frame
from core.llm import load_prompt_template
from core.settings import get_env
from core.textutil import phone_digits as digits_of
from core.zipcode import fill_zip_codes

_TRIGGER = "c2o_live_search_trigger"

db = get_db()
owner, _ = require_staff(db, allow_admin_cookie=True, require_nickname=False)

st.markdown("## 🔎 주문 검색")

broadcasts = dbfns.list_broadcasts(db, owner, limit=50)
broadcast_options: dict[str, str | None] = {"전체": None}
broadcast_options.update({b.title: b.id for b in broadcasts})
broadcast_titles = {b.id: b.title for b in broadcasts}


def _mark_triggered() -> None:
    st.session_state[_TRIGGER] = True


cols = st.columns([2, 2, 2, 2])
name = cols[0].text_input("수령자명", key="search_name", on_change=_mark_triggered)
phone = cols[1].text_input("전화번호", key="search_phone", on_change=_mark_triggered)
chat_name = cols[2].text_input("채팅명", key="search_chat_name", on_change=_mark_triggered)
broadcast_label = cols[3].selectbox("방송", list(broadcast_options.keys()), key="search_broadcast")

triggered = st.session_state.pop(_TRIGGER, False)

if st.button("검색", type="primary") or triggered:
    results = dbfns.search_orders(
        db,
        owner,
        name=name or None,
        phone_digits=digits_of(phone) or None,
        chat_name=chat_name or None,
        broadcast_id=broadcast_options.get(broadcast_label),
        limit=200,
    )

    if not results:
        st.info("검색 결과가 없습니다.")
    else:
        if len(results) >= 200:
            st.warning("최대 200건까지만 표시됩니다. 검색어를 좁혀보세요.")

        table_rows = [
            {
                "방송": broadcast_titles.get(o.broadcast_id, "-"),
                "주문번호": o.order_number,
                "수령자": o.customer_name,
                "전화번호": o.phone,
                "주소": o.full_address,
                "우편번호": o.zip_code or "",
                "상품": "; ".join(f"{i.product_name} {i.option_name} x{i.quantity}" for i in o.items),
                "접수직원": o.staff_name,
                "상태": "취소됨" if o.status == "cancelled" else "접수",
                "접수시각": o.created_at_kst,
            }
            for o in results
        ]
        st.dataframe(table_rows, width="stretch", hide_index=True)

        if st.button("📮 우편번호 채우기 → 엑셀 다운로드", key="search_export_button"):
            config = load_config()
            juso_key = get_env("JUSO_API_KEY")
            gemini_key = dbfns.get_gemini_api_key(db, owner) or ""

            blank_zip_orders = [o for o in results if not o.zip_code]
            if blank_zip_orders:
                prompt_template = load_prompt_template(config["prompts"]["address_to_search"])
                fill_results = fill_zip_codes(
                    blank_zip_orders,
                    juso_api_key=juso_key,
                    gemini_api_key=gemini_key,
                    model=config["gemini"]["model"],
                    temperature=config["gemini"]["temperature"],
                    prompt_template=prompt_template,
                )
                for order in blank_zip_orders:
                    result = fill_results[order.id]
                    dbfns.update_order_zip(db, order.id, result.zip_code, result.search_address)
                    order.zip_code = result.zip_code or order.zip_code
                    order.search_address = result.search_address or order.search_address

            live_output = config["live_output"]
            frame = rows_to_frame(results, config["live_output_columns"], live_output["row_mode"])
            excel_bytes = build_excel(
                frame, None, live_output["sheet_name"], live_output["review_sheet_name"]
            )
            st.download_button(
                "⬇️ 엑셀 파일 받기",
                data=excel_bytes,
                file_name="검색결과.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="search_excel_download",
            )
