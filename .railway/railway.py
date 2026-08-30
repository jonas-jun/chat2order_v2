"""Railway Infrastructure as Code 정의 (구 railway.json 대체).

수정 후에는 반드시 `railway config plan` 으로 실제 환경과의 diff 를 확인한 뒤
`railway config apply` 한다. 이 파일이 선언하지 않은 항목은 지워질 수 있다.

이 저장소는 Railway 프로젝트 `chat2order` 안의 `chat2order_v2` 서비스 하나만
소유한다. 같은 프로젝트의 v1(`chat2order`) 서비스는 저장소가 달라 여기서 다루지
않으므로 서비스 단위 partial 로 선언한다.

작성/적용에는 `pip install railway-sdk` 가 필요하다. 런타임 의존성이 아니므로
requirements.txt 에는 넣지 않는다.
"""

from railway_sdk import define_railway, github, preserve, project, service

PARTIAL = "chat2order_v2"

# Streamlit 은 Railway 가 주는 $PORT 로 열어야 하고, 컨테이너 밖에서 접근할 수
# 있도록 0.0.0.0 에 바인딩한다. headless 는 실행 시 브라우저를 띄우지 않게 한다.
START_COMMAND = (
    "python -m streamlit run app.py"
    " --server.port $PORT --server.address 0.0.0.0 --server.headless true"
)

# 값은 Railway 에만 두고 여기서는 키만 선언한다. preserve() 는 "이 변수는 내가
# 아는 변수이니 지우지 말고 현재 값을 유지하라"는 뜻이다. 선언에서 빠진 변수는
# apply 때 삭제되므로, Railway 에 변수를 추가하면 이 목록에도 추가해야 한다.
MANAGED_VARIABLES = (
    "AUTH_SECRET",
    "JUSO_API_KEY",
    "SUPABASE_KEY",
    "SUPABASE_URL",
    "TZ",
)


@define_railway
def main(ctx=None):
    web = service(
        "chat2order_v2",
        source=github("jonas-jun/chat2order_v2", branch="main"),
        # 서비스 설정에는 RAILPACK 으로 남아 있지만, 실제 빌드는 railway.json 의
        # 이 값을 따라 Nixpacks 로 돌고 있다(빌드 로그: "using build driver
        # nixpacks-v1.41.0"). 마이그레이션에서 빌더를 바꾸지 않으려면 NIXPACKS 여야 한다.
        build={"builder": "NIXPACKS"},
        start=START_COMMAND,
        # 앱이 죽으면 자동 복구. 구 railway.json 의 restartPolicyType 과 같은 값.
        deploy={"restartPolicyType": "ON_FAILURE"},
        env={name: preserve() for name in MANAGED_VARIABLES},
        networking={
            # 운영 공개 도메인. core/links.py 가 RAILWAY_PUBLIC_DOMAIN 으로 읽어
            # 직원 공유 링크를 만든다 (#16).
            "serviceDomains": {"chat2order-live.up.railway.app": {}},
            "privateNetworkEndpoint": "chat2orderv2",
        },
    )
    return project("chat2order", resources=[web])
