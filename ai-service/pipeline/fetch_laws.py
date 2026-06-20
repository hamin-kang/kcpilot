"""국가법령정보 API에서 법령·행정규칙 본문을 받아 data/raw/law_api/ 에 그대로 저장한다.

설계 원칙:
- raw 레이어는 "출처가 준 것을 불변으로 박제"하는 곳이다. 본문 JSON은 가공 없이 덤프한다.
- 검색어가 아니라 **식별자(법령ID / 행정규칙ID)로 핀**을 박는다. 검색 결과 첫 건을
  매번 추측하면, 개정될 때 다른 문서를 박제할 수 있어 raw의 재현성·동일성이 깨진다.
- 받은 본문이 기대한 문서가 맞는지 검증한다. API는 인증 실패·오류 시에도 HTTP 200에
  빈 응답을 주므로, 본문 키 존재와 명칭 일치를 확인한 뒤에만 저장한다.
- 언제 받은 어느 시행일 버전인지를 _manifest.json에 기록한다(provenance).

법령 vs 행정규칙 — 본문 요청 방식이 다르다:
- 법령: lawService에 법령ID를 주면 항상 '현행' 본문이 온다. (ID 핀 하나로 끝)
- 행정규칙(고시): lawService가 ID가 아니라 '행정규칙일련번호'를 받는데, 이 번호는
  개정마다 바뀐다. 그래서 행정규칙ID로 검색 → '현행' 일련번호를 골라 → 그 번호로 본문.
  (전파법 적합성평가 대상 품목은 전파법이 아니라 이 고시 별표1에 있어 꼭 필요하다.)

핀 갱신(새 문서 추가/ID 확인):
    uv run python pipeline/fetch_laws.py --discover "전파법"
    uv run python pipeline/fetch_laws.py --discover-admrul "방송통신기자재등의 적합성평가에 관한 고시"

실행:
    uv run python pipeline/fetch_laws.py
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import settings

SEARCH_URL = "http://www.law.go.kr/DRF/lawSearch.do"
SERVICE_URL = "http://www.law.go.kr/DRF/lawService.do"
OUT_DIR = ROOT / "data" / "raw" / "law_api"

# (법령ID, 저장 slug, 기대 법령명) — 법령ID로 핀을 박는다.
LAWS = [
    ("001459", "safety_act",      "전기용품 및 생활용품 안전관리법"),
    ("004698", "safety_decree",   "전기용품 및 생활용품 안전관리법 시행령"),
    ("008044", "safety_rule",     "전기용품 및 생활용품 안전관리법 시행규칙"),
    ("012070", "children_act",    "어린이제품 안전 특별법"),
    ("012297", "children_decree", "어린이제품 안전 특별법 시행령"),
    ("012304", "children_rule",   "어린이제품 안전 특별법 시행규칙"),
    ("001732", "wave_act",        "전파법"),
    ("004771", "wave_decree",     "전파법 시행령"),
    ("012057", "wave_rule",       "전파법 시행규칙"),
]

# (행정규칙ID, 저장 slug, 기대 명칭, PDF로도 받을 별표번호들) — 전자파 적합성평가 대상 품목 고시.
# 별표내용 JSON은 ASCII 표라 파싱이 불리해서, 칸 선이 있는 PDF를 함께 받아 둔다(파서가 PDF를 씀).
ADMRULES = [
    ("38724", "emc_conformity", "방송통신기자재등의 적합성평가에 관한 고시", ["0001"]),
]


def _oc() -> str:
    oc = settings.LAW_API_OC
    if not oc:
        raise SystemExit("LAW_API_OC가 없습니다. ai-service/.env에 LAW_API_OC=<기관코드>를 넣으세요.")
    return oc


def _search(target: str, query: str) -> list[dict]:
    res = requests.get(SEARCH_URL, params={"OC": _oc(), "target": target, "type": "JSON", "query": query})
    res.raise_for_status()
    root_key = "LawSearch" if target == "law" else "AdmRulSearch"
    items = res.json().get(root_key, {}).get(target, [])
    return [items] if isinstance(items, dict) else items


def discover(query: str) -> None:
    """법령명으로 검색해 법령ID·현행여부·시행일을 출력한다(LAWS 핀 갱신용)."""
    items = _search("law", query)
    if not items:
        print(f"검색 결과 없음: {query}")
        return
    for it in items:
        mark = "← 현행" if it.get("현행연혁코드") == "현행" else ""
        print(f"  법령ID={it['법령ID']}  시행일={it.get('시행일자')}  {it['법령명한글']} {mark}")


def discover_admrul(query: str) -> None:
    """고시명으로 검색해 행정규칙ID·일련번호·현행여부를 출력한다(ADMRULES 핀 갱신용)."""
    items = _search("admrul", query)
    if not items:
        print(f"검색 결과 없음: {query}")
        return
    for it in items:
        mark = "← 현행" if it.get("현행연혁구분") == "현행" else ""
        print(f"  행정규칙ID={it['행정규칙ID']}  일련={it['행정규칙일련번호']}  시행일={it.get('시행일자')}  {it['행정규칙명']} {mark}")


def fetch_law(law_id: str, expected_name: str) -> tuple[dict, dict]:
    """법령ID로 현행 본문을 받아 (본문JSON, provenance) 를 반환한다."""
    res = requests.get(SERVICE_URL, params={"OC": _oc(), "target": "law", "type": "JSON", "ID": law_id})
    res.raise_for_status()
    data = res.json()

    basic = data.get("법령", {}).get("기본정보")
    if not basic:
        raise RuntimeError(f"빈/비정상 응답 (인증 실패 또는 잘못된 ID일 수 있음): ID={law_id}")
    got_name = basic.get("법령명_한글", "")
    if got_name != expected_name:
        raise RuntimeError(f"법령명 불일치: 기대='{expected_name}' 실제='{got_name}' (ID={law_id})")

    provenance = {
        "target": "law",
        "doc_id": law_id,
        "name": got_name,
        "effective_date": basic.get("시행일자"),
        "promulgation_date": basic.get("공포일자"),
        "source_url": f"{SERVICE_URL}?target=law&type=JSON&ID={law_id}",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    return data, provenance


def fetch_admrul(adm_id: str, expected_name: str) -> tuple[dict, dict]:
    """행정규칙ID로 '현행' 일련번호를 찾아 그 본문을 받는다.

    행정규칙 본문 API는 ID가 아니라 일련번호(개정마다 바뀜)를 받으므로,
    검색에서 같은 ID + 명칭 + '현행' 항목의 일련번호를 골라 사용한다.
    """
    serial = None
    for it in _search("admrul", expected_name):
        if (it.get("행정규칙ID") == adm_id
                and it.get("행정규칙명") == expected_name
                and it.get("현행연혁구분") == "현행"):
            serial = it["행정규칙일련번호"]
            break
    if serial is None:
        raise RuntimeError(f"현행 행정규칙을 못 찾음: ID={adm_id} '{expected_name}'")

    res = requests.get(SERVICE_URL, params={"OC": _oc(), "target": "admrul", "type": "JSON", "ID": serial})
    res.raise_for_status()
    data = res.json()

    basic = data.get("AdmRulService", {}).get("행정규칙기본정보")
    if not basic:
        raise RuntimeError(f"빈/비정상 응답: 행정규칙 일련번호={serial}")
    got_name = basic.get("행정규칙명", "")
    if got_name != expected_name:
        raise RuntimeError(f"행정규칙명 불일치: 기대='{expected_name}' 실제='{got_name}'")

    provenance = {
        "target": "admrul",
        "doc_id": adm_id,
        "serial": serial,
        "name": got_name,
        "effective_date": basic.get("시행일자"),
        "promulgation_no": basic.get("발령번호"),
        "source_url": f"{SERVICE_URL}?target=admrul&type=JSON&ID={serial}",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    return data, provenance


def download_appendix_pdfs(data: dict, slug: str, numbers: list[str]) -> list[dict]:
    """고시 본문 JSON에 담긴 별표 PDF 링크로 해당 별표 PDF를 받아 저장한다(재현용).

    저장 파일명: {slug}_appx{N}.pdf  (예: emc_conformity_appx1.pdf)
    """
    units = data["AdmRulService"]["별표"]["별표단위"]
    units = [units] if isinstance(units, dict) else units
    out: list[dict] = []
    for num in numbers:
        unit = next((u for u in units if u.get("별표번호") == num and u.get("별표구분") == "별표"), None)
        if unit is None:
            raise RuntimeError(f"별표 {num}을(를) 못 찾음: {slug}")
        link = unit.get("별표서식PDF파일링크")
        if not link:
            raise RuntimeError(f"별표 {num} PDF 링크 없음: {slug}")
        url = "https://www.law.go.kr" + link
        res = requests.get(url, timeout=30)
        res.raise_for_status()
        if res.content[:4] != b"%PDF":
            raise RuntimeError(f"PDF가 아님(빈응답?): {url}")
        fname = f"{slug}_appx{int(num)}.pdf"
        (OUT_DIR / fname).write_bytes(res.content)
        print(f"  → {fname}  ({len(res.content):,} bytes)")
        out.append({
            "slug": fname[:-4],
            "target": "admrul_pdf",
            "name": unit.get("별표제목", ""),
            "source_url": url,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        })
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--discover", metavar="법령명", help="법령ID 검색만 하고 종료")
    parser.add_argument("--discover-admrul", metavar="고시명", help="행정규칙ID 검색만 하고 종료")
    args = parser.parse_args()

    if args.discover:
        discover(args.discover)
        return
    if args.discover_admrul:
        discover_admrul(args.discover_admrul)
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest: list[dict] = []

    for law_id, slug, expected_name in LAWS:
        print(f"[법령] {expected_name} (ID={law_id})")
        data, prov = fetch_law(law_id, expected_name)
        (OUT_DIR / f"{slug}.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        manifest.append({"slug": slug, **prov})
        print(f"  → {slug}.json  (시행일 {prov['effective_date']})\n")
        time.sleep(0.5)

    for adm_id, slug, expected_name, pdf_appendices in ADMRULES:
        print(f"[고시] {expected_name} (ID={adm_id})")
        data, prov = fetch_admrul(adm_id, expected_name)
        (OUT_DIR / f"{slug}.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        manifest.append({"slug": slug, **prov})
        print(f"  → {slug}.json  (시행일 {prov['effective_date']}, 일련 {prov['serial']})")
        manifest.extend(download_appendix_pdfs(data, slug, pdf_appendices))
        print()
        time.sleep(0.5)

    (OUT_DIR / "_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"완료. {len(manifest)}건 저장 + _manifest.json 기록.")


if __name__ == "__main__":
    main()
