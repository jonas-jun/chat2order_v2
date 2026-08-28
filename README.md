# chat2order_v2

라이브 방송 중 CS 직원이 주문을 직접 입력하는 경량 웹 앱 (Streamlit + Supabase).

## 로컬 실행

requirements 가 설치된 conda 환경 `c2o-v2` 를 활성화하고, `.env` 를 환경변수로 올린
뒤 Streamlit 을 실행한다. 앱은 `.env` 를 자동 로드하지 않고 `os.getenv` 로 읽으므로
`source` 가 필요하다.

```bash
conda activate c2o-v2
set -a && source .env && set +a
streamlit run app.py
```

실행하면 http://localhost:8501 이 열린다. 포트를 바꾸려면 `--server.port 8502` 를 뒤에
붙인다.

### 페이지

내비게이션 바는 숨겨져 있어 URL 로 직접 접근한다.

| 페이지 | URL | 접근 |
| --- | --- | --- |
| 관리자 (방송 생성·상품 CSV 업로드·엑셀 추출) | `/` | Supabase `accounts` 계정 |
| 주문 입력 | `/order?b=<방송id>&t=<직원토큰>` | 직원 토큰 링크 |
| 주문 검색 | `/search` | 관리자 |

## 테스트

```bash
conda activate c2o-v2
python -m pytest
```
