import io
from pathlib import Path

import pandas as pd

from core.models import ProductInput

REQUIRED_COLUMNS = ("상품명", "옵션내용", "판매가")
DEFAULT_OPTION_NAME = "단일상품"

# 재고 내보내기(stk_forInOut_*.csv) 컬럼. 판매가 대신 '판매단가' 를 쓴다.
INVENTORY_REQUIRED_COLUMNS = ("상품명", "옵션내용", "판매단가")


def read_csv_any_encoding(source) -> pd.DataFrame:
    """utf-8-sig → cp949 → euc-kr 순으로 인코딩을 시도해 CSV 를 읽는다."""
    if isinstance(source, (str, Path)):
        raw = io.BytesIO(Path(source).read_bytes())
    else:
        raw = io.BytesIO(source.getvalue())  # Streamlit UploadedFile

    for encoding in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            raw.seek(0)
            return pd.read_csv(raw, encoding=encoding, encoding_errors="strict")
        except (UnicodeDecodeError, LookupError):
            continue
    raw.seek(0)
    return pd.read_csv(raw, encoding="utf-8", encoding_errors="replace")


def parse_price(text: object) -> int:
    """"78,000원" 같은 표기에서 쉼표·원·공백을 제거하고 정수(원)로 변환한다."""
    if text is None or (isinstance(text, float) and pd.isna(text)):
        raise ValueError("판매가가 비어 있습니다")
    cleaned = str(text).strip().replace(",", "").replace("원", "").replace(" ", "")
    if not cleaned:
        raise ValueError("판매가가 비어 있습니다")
    try:
        return int(float(cleaned))
    except ValueError as exc:
        raise ValueError(f"판매가를 숫자로 변환할 수 없습니다: {text!r}") from exc


def parse_products_csv(source) -> list[ProductInput]:
    """업로드된 상품 CSV 를 상품옵션 목록으로 파싱한다.

    두 가지 포맷을 자동으로 받는다.

    * 표준 상품 CSV — ``판매가`` 컬럼이 있는 경우. (§4.1 규격)
    * 재고 내보내기(stk_forInOut_*.csv) — ``판매가`` 없이 ``판매단가`` 컬럼만
      있는 경우. v1 ``generate_catalog_from_csv`` 와 같은 규칙으로 상품·옵션을
      뽑고 ``판매단가`` 를 가격으로 붙인다.

    어느 컬럼도 없으면 두 포맷을 모두 안내하는 오류를 낸다.
    """
    df = read_csv_any_encoding(source)

    if "판매가" not in df.columns and "판매단가" in df.columns:
        return _inventory_products_from_df(df)

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"CSV에 {', '.join(REQUIRED_COLUMNS)} 컬럼이 필요합니다"
            f" (재고 파일이면 판매가 대신 판매단가). 발견된 컬럼: {list(df.columns)}"
        )
    return _standard_products_from_df(df)


def parse_inventory_products(source) -> list[ProductInput]:
    """재고 CSV(상품명·옵션내용·판매단가)만 파싱한다 (스크립트/테스트용).

    포맷을 자동 판별하는 :func:`parse_products_csv` 와 달리 재고 포맷을 강제한다.
    """
    df = read_csv_any_encoding(source)
    missing = [c for c in INVENTORY_REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"CSV에 {', '.join(INVENTORY_REQUIRED_COLUMNS)} 컬럼이 필요합니다. "
            f"발견된 컬럼: {list(df.columns)}"
        )
    return _inventory_products_from_df(df)


def _inventory_products_from_df(df: pd.DataFrame) -> list[ProductInput]:
    """재고 CSV 규칙: 상품·옵션 등장 순서 유지, 상품 내 옵션 중복 제거,
    빈 옵션 행 제외, ``판매단가`` 를 가격으로(빈 값은 0 원, 0 원도 포함)."""
    # (상품명 등장 순서, 상품 내 옵션 등장 순서)를 유지하려고 dict 를 쓴다.
    # 값은 {옵션내용: 판매단가} 로, 같은 (상품, 옵션) 은 첫 행의 가격을 취한다.
    catalog: dict[str, dict[str, int]] = {}
    for _, row in df.iterrows():
        product = str(row["상품명"]).strip() if pd.notna(row["상품명"]) else ""
        if not product:
            continue

        option = str(row["옵션내용"]).strip() if pd.notna(row["옵션내용"]) else ""
        options = catalog.setdefault(product, {})
        if not option or option in options:
            continue  # 빈 옵션·중복 옵션은 건너뜀 (v1 카탈로그 규칙)

        raw_price = row["판매단가"]
        blank_price = raw_price is None or (
            isinstance(raw_price, float) and pd.isna(raw_price)
        ) or str(raw_price).strip() == ""
        options[option] = 0 if blank_price else parse_price(raw_price)

    return [
        ProductInput(product_name=product, option_name=option, price=price)
        for product, options in catalog.items()
        for option, price in options.items()
    ]


def _standard_products_from_df(df: pd.DataFrame) -> list[ProductInput]:
    """표준 상품 CSV 규칙: 빈 행 건너뜀, 빈 옵션은 '단일상품', (상품, 옵션)
    중복은 첫 행만, 판매가 파싱 실패는 행 번호를 포함해 업로드 전체를 거부."""
    products: list[ProductInput] = []
    seen: set[tuple[str, str]] = set()
    for idx, row in df.iterrows():
        line_no = idx + 2  # 헤더 제외, CSV 파일 기준 행 번호

        raw_name = row["상품명"]
        product_name = str(raw_name).strip() if pd.notna(raw_name) else ""
        if not product_name:
            continue  # 빈 행은 건너뜀

        raw_option = row["옵션내용"]
        option_name = str(raw_option).strip() if pd.notna(raw_option) else ""
        if not option_name:
            option_name = DEFAULT_OPTION_NAME

        try:
            price = parse_price(row["판매가"])
        except ValueError as exc:
            raise ValueError(f"{line_no}행: {exc}") from exc

        key = (product_name, option_name)
        if key in seen:
            continue  # 중복 행은 첫 행만 취함
        seen.add(key)

        products.append(
            ProductInput(product_name=product_name, option_name=option_name, price=price)
        )

    return products
