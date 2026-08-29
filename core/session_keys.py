"""session_state 키 상수 모음.

문자열 리터럴을 직접 쓰면 오타·불일치를 컴파일 시점에 잡을 수 없어 상수로 모아둔다.
"""

LOGGED_IN_USER = "c2o_live_logged_in_user"
STAFF_NICKNAME = "c2o_live_staff_nickname"
GEMINI_API_KEY = "c2o_live_gemini_api_key"

SELECTED_BROADCAST_ID = "c2o_live_selected_broadcast_id"
NEW_BROADCAST_PRODUCTS = "c2o_live_new_broadcast_products"
CSV_UPLOADER_VERSION = "c2o_live_csv_uploader_version"

CART = "c2o_live_cart"
CART_VERSION = "c2o_live_cart_version"
EDITING_ORDER_ID = "c2o_live_editing_order_id"
ORDER_FORM_VERSION = "c2o_live_order_form_version"
ADDRESS_CANDIDATES = "c2o_live_address_candidates"
PENDING_ORDERS = "c2o_live_pending_orders"
