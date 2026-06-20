"""safetykorea Open API에서 리콜 데이터를 받아 data/raw/recalls/ 에 저장한다.

API 키 발급:
    safetykorea@korea.kr 로 신청서 이메일 발송 → 1~2 영업일 후 키 발급
    발급받은 키를 ai-service/.env 에 추가: SAFETYKOREA_API_KEY=...

실행:
    uv run python pipeline/fetch_recalls.py
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import settings

OUT_DIR = ROOT / "data" / "raw" / "recalls"


def _key() -> str:
    key = getattr(settings, "SAFETYKOREA_API_KEY", "")
    if not key:
        raise SystemExit(
            "SAFETYKOREA_API_KEY가 없습니다.\n"
            "safetykorea@korea.kr 에 신청서 이메일 발송 후 발급받은 키를 .env에 추가하세요.\n"
            "예: SAFETYKOREA_API_KEY=your_key_here"
        )
    return key


def main() -> None:
    # TODO: API 키 발급 후 실제 엔드포인트·파라미터 확인해서 구현
    # 아래는 safetykorea API 명세서 수령 후 채울 자리
    raise NotImplementedError(
        "safetykorea Open API 키 발급 대기 중.\n"
        "키 발급 후 API 명세서 확인해서 구현 예정."
    )


if __name__ == "__main__":
    main()
