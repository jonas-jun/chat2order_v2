import io
from pathlib import Path

import pandas as pd

from core.models import ProductInput

REQUIRED_COLUMNS = ("상품명", "옵션내용", "판매가")
DEFAULT_OPTION_NAME = "단일상품"


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
    """상품 CSV(상품명·옵션내용·판매가)를 파싱한다.

    빈 행은 건너뛰고, 옵션내용이 비어 있으면 '단일상품'으로 채운다.
    (상품명, 옵션내용) 중복 행은 첫 행만 취한다. 판매가 파싱 실패는
    행 번호(헤더 제외, 2행부터)를 포함한 오류로 업로드 전체를 거부한다.
    """
    df = read_csv_any_encoding(source)

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"CSV에 {', '.join(REQUIRED_COLUMNS)} 컬럼이 필요합니다. 발견된 컬럼: {list(df.columns)}"
        )

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
