import os
from datetime import timedelta, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 서비스 기준 타임존. 배포 서버의 로컬 타임존(Railway 기본값 UTC)과 무관하게
# 시각 표시·주문번호 날짜를 한국 시각으로 고정하기 위해 사용한다.
KST = timezone(timedelta(hours=9))


def get_env(name: str, default: str = "") -> str:
    """실행 환경에서 설정값을 읽습니다."""
    return os.getenv(name, default)
