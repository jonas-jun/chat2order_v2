import json
import re

from google import genai
from google.genai import types


def _gemini_client(api_key: str):
    """API 키를 정제하고 Gemini 클라이언트를 생성한다."""
    clean_key = re.sub(r"[^\x20-\x7E]", "", api_key).strip()
    return genai.Client(api_key=clean_key)


def _generate_json(client, model: str, prompt: str, schema, temperature: float):
    """공통 JSON structured output 호출."""
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
            temperature=temperature,
        ),
    )
    return json.loads(response.text)


def extract_search_address(
    api_key: str,
    address: str,
    model: str,
    temperature: float,
    prompt_template: str,
) -> str | None:
    """Gemini로 단일 주소에서 우편번호 검색용 도로명주소를 추출합니다."""
    client = _gemini_client(api_key)

    prompt = prompt_template.format(address=address)

    try:
        result = _generate_json(
            client=client,
            model=model,
            prompt=prompt,
            schema=str | None,
            temperature=temperature,
        )
        return result if isinstance(result, str) and result.strip() else None
    except Exception:
        return None
