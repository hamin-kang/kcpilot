"""safetykorea Open API에서 국내 리콜 데이터를 받아 data/recalls.json 에 저장한다.

API 명세: Open API 인터페이스 설계서 v2.0 (2025-06-30)
  - 인증: HTTP Header AuthKey: {서비스ID}
  - 엔드포인트: GET /openapi/api/recall/recallList.json
  - 파라미터: conditionKey (검색구분), conditionValue (검색어)
  - 최대 1,000건/요청, 페이지네이션 없음

전략: KC 인증 관련 품목(전기용품·어린이제품·생활용품 등) 키워드로
      여러 번 검색하고 recallUid 기준으로 중복 제거 후 저장한다.

실행:
    uv run python pipeline/fetch_recalls.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import settings

BASE_URL = "http://www.safetykorea.kr/openapi/api/recall/recallList.json"
RAW_DIR = ROOT / "data" / "raw" / "recalls"
OUT_FILE = RAW_DIR / "recalls.json"

# KC 인증 관련 주요 품목 키워드 — 각각 최대 1,000건 수집 후 중복 제거
SEARCH_KEYWORDS = [
    "전기",
    "어린이",
    "가전",
    "완구",
    "충전",
    "배터리",
    "조명",
    "가습기",
    "헤어",
    "생활",
]


def _auth_headers() -> dict:
    key = getattr(settings, "SAFETYKOREA_API_KEY", "").strip()
    if not key:
        raise SystemExit(
            "SAFETYKOREA_API_KEY가 없습니다.\n"
            "ai-service/.env에 SAFETYKOREA_API_KEY=발급받은키 를 추가하세요."
        )
    return {"AuthKey": key}


def _fetch(keyword: str) -> list[dict]:
    """키워드로 국내 리콜 목록을 조회한다."""
    resp = requests.get(
        BASE_URL,
        params={"conditionKey": "recallProductName", "conditionValue": keyword},
        headers=_auth_headers(),
        timeout=30,
    )
    resp.raise_for_status()
    body = resp.json()
    code = str(body.get("resultCode", ""))
    if code == "2004":  # No Data
        return []
    if code != "2000":
        print(f"  [{keyword}] 응답 오류: {body.get('resultMsg')} (code={code})")
        return []
    return body.get("resultData") or []


def _normalize(item: dict) -> dict:
    """API 응답을 ingest.py가 기대하는 형식으로 변환한다.

    ingest.py의 load_recall_documents()는 title·product·reason 세 필드를
    임베딩 텍스트로 쓰고 나머지를 metadata로 저장한다.
    """
    product_name = item.get("recallProductName") or ""
    brand = item.get("recallBrandName") or ""
    model = item.get("recallModelName") or ""
    item_name = item.get("productItemName") or ""
    harm = item.get("harmDscr") or ""
    accident = item.get("accidentCaseDscr") or ""
    recall_type = item.get("recallTypeName") or ""
    action = item.get("publishActionDscr") or ""

    title_parts = [product_name]
    if brand:
        title_parts.append(brand)
    title = " ".join(title_parts)

    product_parts = [product_name]
    if model:
        product_parts.append(f"모델: {model}")
    if item_name:
        product_parts.append(f"품목: {item_name}")
    product = " / ".join(product_parts)

    reason_parts = []
    if recall_type:
        reason_parts.append(recall_type)
    if harm:
        reason_parts.append(f"결함: {harm}")
    if accident:
        reason_parts.append(f"위해: {accident}")
    if action:
        reason_parts.append(f"조치: {action}")
    reason = " | ".join(reason_parts) if reason_parts else "사유 미상"

    return {
        "title": title,
        "product": product,
        "reason": reason,
        # 원본 필드 보존 (workflow recall_node가 metadata로 활용)
        "recallUid": item.get("recallUid"),
        "recallProductName": product_name,
        "recallBrandName": brand,
        "recallModelName": model,
        "recallTypeName": recall_type,
        "publishDate": item.get("publishDate"),
        "harmDscr": harm,
        "accidentCaseDscr": accident,
        "publishActionDscr": action,
        "makerName": item.get("makerName"),
        "recallCmpnyName": item.get("recallCmpnyName"),
    }


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    seen: set[str] = set()
    all_items: list[dict] = []

    for keyword in SEARCH_KEYWORDS:
        raw = _fetch(keyword)
        new = 0
        for item in raw:
            uid = str(item.get("recallUid", ""))
            if uid and uid not in seen:
                seen.add(uid)
                all_items.append(_normalize(item))
                new += 1
        print(f"  [{keyword}] {len(raw)}건 수신, {new}건 신규")
        time.sleep(0.3)  # API 과부하 방지

    OUT_FILE.write_text(
        json.dumps(all_items, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n완료. {len(all_items)}건 → {OUT_FILE}")
    print("이제 ingest.py를 다시 실행하면 kc_recalls 컬렉션에 적재됩니다.")
    print("  DATABASE_URL=... uv run python pipeline/ingest.py")
    print("\n참고: ingest.py는 data/raw/recalls/recalls_domestic.json 을 읽습니다.")


if __name__ == "__main__":
    main()
