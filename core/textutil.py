import re

import pandas as pd


def format_phone_number(phone: str | None) -> str | None:
    """전화번호에서 숫자만 추출 후 010-XXXX-XXXX 형식으로 변환합니다."""
    if phone is None or pd.isna(phone):
        return None
    phone = str(phone)
    if not phone:
        return phone
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 11 and digits.startswith("010"):
        return f"{digits[:3]}-{digits[3:7]}-{digits[7:]}"
    return phone


def normalize_zip_code(zip_code: object) -> str:
    """우편번호를 문자열(5자리)로 정규화합니다."""
    if zip_code is None or pd.isna(zip_code):
        return ""

    raw = str(zip_code).strip()
    if not raw:
        return ""

    digits = re.sub(r"\D", "", raw)
    if not digits:
        return raw

    if len(digits) <= 5:
        return digits.zfill(5)

    return digits


def phone_digits(phone: str | None) -> str:
    """검색·중복 비교용으로 숫자만 남긴다. (v2 신규)"""
    return re.sub(r"\D", "", phone or "")
