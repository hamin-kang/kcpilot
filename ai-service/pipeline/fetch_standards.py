"""전기용품·어린이제품·생활용품 안전기준 고시 첨부 파일을 data/raw/standards/ 에 저장한다.

- 전기용품 KC 계열 (72개): PDF 첨부 다운로드 (없으면 HWP)
- 어린이제품·생활용품 (8개): PDF 첨부 다운로드 (없으면 HWP)
  JSON 별표 본문은 ASCII 표라 파싱 불가 — 첨부 파일이 실제 쓸 데이터.

실행:
    uv run python pipeline/fetch_standards.py
"""
from __future__ import annotations

import json
import re
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
OUT_DIR = ROOT / "data" / "raw" / "standards"


def _oc() -> str:
    oc = settings.LAW_API_OC
    if not oc:
        raise SystemExit("LAW_API_OC가 없습니다. ai-service/.env에 LAW_API_OC=<기관코드>를 넣으세요.")
    return oc


def _name_to_slug(name: str) -> str:
    """고시명 → 파일명용 slug. 예: '전기용품 안전기준(KC 60335-2-23)' → 'kc_60335_2_23'"""
    m = re.search(r'KC\s+([\d\-]+)', name)
    if m:
        return "kc_" + m.group(1).replace("-", "_")
    # KC 코드 없는 경우 (어린이·생활용품 기준)
    slug = re.sub(r'[^\w가-힣]', '_', name)
    slug = re.sub(r'_+', '_', slug).strip('_')
    return slug[:60]


def _get_current_serial(adm_id: str, name: str) -> str | None:
    """행정규칙ID + 명칭으로 현행 일련번호를 찾는다."""
    r = requests.get(SEARCH_URL, params={"OC": _oc(), "target": "admrul", "type": "JSON", "query": name})
    r.raise_for_status()
    items = r.json().get("AdmRulSearch", {}).get("admrul", [])
    items = [items] if isinstance(items, dict) else items
    for it in items:
        if it.get("행정규칙ID") == adm_id and it.get("현행연혁구분") == "현행":
            return it["행정규칙일련번호"]
    return None


def fetch_all_kc_standards() -> list[dict]:
    """전기용품 안전기준(KC 계열) 현행 고시 목록을 API에서 조회해 반환한다."""
    r = requests.get(SEARCH_URL, params={
        "OC": _oc(), "target": "admrul", "type": "JSON",
        "query": "전기용품 안전기준", "display": 100,
    })
    r.raise_for_status()
    items = r.json().get("AdmRulSearch", {}).get("admrul", [])
    items = [items] if isinstance(items, dict) else items
    return [it for it in items if it.get("현행연혁구분") == "현행" and "KC" in it.get("행정규칙명", "")]


def download_pdf(serial: str, slug: str, name: str) -> dict | None:
    """고시 일련번호로 본문을 조회해 첨부 PDF를 저장한다."""
    r = requests.get(SERVICE_URL, params={"OC": _oc(), "target": "admrul", "type": "JSON", "ID": serial})
    r.raise_for_status()
    svc = r.json().get("AdmRulService", {})

    basic = svc.get("행정규칙기본정보", {})
    if not basic:
        print(f"  ⚠ 빈 응답: {name}")
        return None

    files_block = svc.get("첨부파일", {})
    links = files_block.get("첨부파일링크", [])
    names = files_block.get("첨부파일명", [])
    links = [links] if isinstance(links, str) else (links or [])
    names = [names] if isinstance(names, str) else (names or [])

    # 개정이유서 제외, 안전기준 본문 파일 우선 (PDF 우선, 없으면 HWP)
    def _is_content_file(n: str) -> bool:
        return "이유서" not in n and "제개정" not in n

    pdf_pairs = [(n, l) for n, l in zip(names, links) if n.lower().endswith(".pdf") and _is_content_file(n)]
    hwp_pairs = [(n, l) for n, l in zip(names, links) if (n.lower().endswith(".hwp") or n.lower().endswith(".hwpx")) and _is_content_file(n)]

    if pdf_pairs:
        fname, link = pdf_pairs[0]
        ext = ".pdf"
    elif hwp_pairs:
        fname, link = hwp_pairs[0]
        ext = ".hwp" if fname.lower().endswith(".hwp") else ".hwpx"
        print(f"  ⚠ PDF 없음, HWP로 대체: {fname}")
    else:
        print(f"  ⚠ 파일 없음: {name}")
        return None

    url = "https://www.law.go.kr" + link if link.startswith("/") else link
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()

    out_path = OUT_DIR / f"{slug}{ext}"
    out_path.write_bytes(resp.content)

    return {
        "slug": slug,
        "target": f"admrul_{ext.lstrip('.')}",
        "name": name,
        "effective_date": basic.get("시행일자"),
        "source_url": url,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def download_attachments(serial: str, slug: str, name: str) -> list[dict]:
    """어린이제품·생활용품 기준 첨부 파일(PDF 우선, 없으면 HWP)을 받는다.

    JSON 별표가 ASCII 표라 파싱 불가 — 첨부 파일이 실제 쓸 데이터.
    첨부가 여러 개면 _appx1, _appx2 ... 로 구분해 저장한다.
    """
    r = requests.get(SERVICE_URL, params={"OC": _oc(), "target": "admrul", "type": "JSON", "ID": serial})
    r.raise_for_status()
    svc = r.json().get("AdmRulService", {})
    basic = svc.get("행정규칙기본정보", {})
    if not basic:
        print(f"  ⚠ 빈 응답: {name}")
        return []

    files_block = svc.get("첨부파일", {})
    links = files_block.get("첨부파일링크", [])
    fnames = files_block.get("첨부파일명", [])
    links = [links] if isinstance(links, str) else (links or [])
    fnames = [fnames] if isinstance(fnames, str) else (fnames or [])

    def _is_content(n: str) -> bool:
        return "이유서" not in n and "제개정" not in n

    pdf_pairs = [(n, l) for n, l in zip(fnames, links) if n.lower().endswith(".pdf") and _is_content(n)]
    hwp_pairs = [(n, l) for n, l in zip(fnames, links) if (n.lower().endswith(".hwp") or n.lower().endswith(".hwpx")) and _is_content(n)]
    attach_pairs = pdf_pairs if pdf_pairs else hwp_pairs

    if not attach_pairs:
        print(f"  ⚠ 첨부파일 없음: {name}")
        return []

    provenance = []
    for i, (fname, link) in enumerate(attach_pairs):
        ext = "." + fname.rsplit(".", 1)[-1].lower()
        suffix = f"_appx{i+1}" if len(attach_pairs) > 1 else ""
        url = "https://www.law.go.kr" + link if link.startswith("/") else link
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        file_slug = f"{slug}{suffix}"
        (OUT_DIR / f"{file_slug}{ext}").write_bytes(resp.content)
        print(f"  → {file_slug}{ext}  ({len(resp.content):,} bytes)")
        provenance.append({
            "slug": file_slug,
            "target": f"admrul_{ext.lstrip('.')}",
            "name": name,
            "effective_date": basic.get("시행일자"),
            "source_url": url,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        })
    return provenance


# 어린이제품·생활용품 안전기준 (JSON으로 본문이 오는 것들)
JSON_STANDARDS = [
    ("48447",   "안전인증대상 어린이제품의 안전기준"),
    ("48452",   "안전확인대상 어린이제품의 안전기준"),
    ("48453",   "개별안전기준이 있는 공급자적합성확인대상 어린이제품"),
    ("48454",   "어린이제품 공통안전기준"),
    ("2000624", "안전인증대상생활용품의 안전기준"),
    ("2048545", "안전확인대상생활용품의 안전기준"),
    ("2049510", "공급자적합성확인대상 생활용품의 안전기준"),
    ("63445",   "안전기준준수대상생활용품의 안전기준"),
]


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest: list[dict] = []

    # 1. 전기용품 KC 계열 PDF (동적 목록 조회)
    print("전기용품 안전기준(KC 계열) PDF 수집 중...")
    kc_standards = fetch_all_kc_standards()
    print(f"  현행 고시 {len(kc_standards)}개 발견\n")

    for it in kc_standards:
        adm_id = it["행정규칙ID"]
        name = it["행정규칙명"]
        serial = it["행정규칙일련번호"]
        slug = _name_to_slug(name)
        print(f"[PDF] {name}")
        prov = download_pdf(serial, slug, name)
        if prov:
            manifest.append(prov)
            print(f"  → {slug}.pdf  (시행일 {prov['effective_date']})")
        print()
        time.sleep(0.5)

    # 2. 어린이제품·생활용품 안전기준 JSON
    print("어린이제품·생활용품 안전기준 JSON 수집 중...\n")
    for adm_id, name in JSON_STANDARDS:
        slug = _name_to_slug(name)
        print(f"[JSON] {name}")
        serial = _get_current_serial(adm_id, name)
        if not serial:
            print(f"  ⚠ 현행 일련번호 못 찾음\n")
            continue
        provs = download_attachments(serial, slug, name)
        if provs:
            manifest.extend(provs)
            print(f"  시행일 {provs[0]['effective_date']}")
        print()
        time.sleep(0.5)

    (OUT_DIR / "_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"완료. {len(manifest)}건 저장 + _manifest.json 기록.")


if __name__ == "__main__":
    main()
