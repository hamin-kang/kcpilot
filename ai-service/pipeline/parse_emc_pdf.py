"""전자파 적합성평가 대상기자재 별표1(PDF)을 전처리·청킹해 data/processed/로 변환한다.

왜 PDF인가:
- 이 별표1은 「방송통신기자재등의 적합성평가에 관한 고시」 별표1로, 전자파 축의 품목→인증등급
  분류표다(전파법·시행령·시행규칙엔 품목 분류 별표가 없어 이 고시가 유일한 출처).
- 현행법령 API의 별표내용 JSON은 1,900줄 넘는 복잡한 ASCII 표라 파싱이 비현실적이다.
  같은 별표를 PDF로 받으면 pdfplumber가 칸 구분을 정확히 추출하므로 PDF로 파싱한다.

설계:
- 페이지마다 헤더 컬럼 구성이 다르다(12열: 적합인증·등록·확인 / 8열: 적합등록·확인만).
  그래서 컬럼 인덱스를 고정하지 않고, 헤더 행의 키워드로 동적 매핑한다.
- 기기부호(HDR11 등)가 있는 행 = 품목 1건. '적합인증/적합등록/자기적합확인' 컬럼의
  ○ 위치로 cert_level을 자동 판정한다.

실행:
    uv run python pipeline/parse_emc_pdf.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))

from preprocess import clean_legal_text, normalize_inline  # noqa: E402

RAW_DIR = ROOT / "data" / "raw" / "law_api"
PDF_PATH = RAW_DIR / "emc_conformity_appx1.pdf"
OUT_DIR = ROOT / "data" / "processed"
SLUG = "emc_conformity"

_CODE = re.compile(r"^[A-Za-z]{2,}[A-Za-z0-9]*\d")   # 기기부호: SA, HDR11, COW12 ...
_NUM_PREFIX = re.compile(r"^\d+\)\s*")
_MAJOR_HEAD = re.compile(r"^[가-힣]\s*\.")            # 대분류 머리: "가.", "나." ...
_CERT_ORDER = ["적합인증", "적합등록", "자기적합확인"]


def _has_circle(cell: str | None) -> bool:
    return bool(cell) and ("○" in cell or "◯" in cell)


def _build_colmap(header_rows: list[list]) -> dict:
    """헤더 행들을 컬럼별로 누적해 의미를 매핑한다."""
    ncol = max(len(r) for r in header_rows)
    coltext = [""] * ncol
    for r in header_rows:
        for i, c in enumerate(r):
            coltext[i] += normalize_inline(c)

    cm = {"name": [], "major": None, "desc": None, "code": None, "cert": {}}
    for i, t in enumerate(coltext):
        if "적합인증" in t:
            cm["cert"][i] = "적합인증"
        elif "적합등록" in t:
            cm["cert"][i] = "적합등록"
        elif "자기적합확인" in t or ("자기" in t and "확인" in t):
            cm["cert"][i] = "자기적합확인"
        elif "기기부호" in t or ("기기" in t and "부호" in t):
            cm["code"] = i
        elif any(k in t for k in ("전자파", "무선", "유선", "인체", "강도", "흡수율",
                                   "적용분야", "적합성평가", "유형", "기타")):
            continue  # ○가 찍히는 적용분야 컬럼·병합 헤더 → 무시
        elif "소분류" in t:
            cm["desc"] = i
        elif "대분류" in t or "대상기자재" in t:
            cm["major"] = i
        elif "중분류" in t or "품목" in t:
            cm["name"].insert(0, i)   # 품목명 최우선
        else:
            cm["name"].append(i)      # 라벨 없는 텍스트 컬럼(품목)
    return cm


def _header_rows(table: list[list]) -> int:
    """테이블 앞쪽에서 ○가 나오기 전까지를 헤더로 본다."""
    n = 0
    for r in table:
        if any(_has_circle(c) for c in r):
            break
        n += 1
    return min(n, 5) if n else 0


def main() -> None:
    if not PDF_PATH.exists():
        raise SystemExit(f"PDF 없음: {PDF_PATH}")

    manifest = json.loads((RAW_DIR / "_manifest.json").read_text(encoding="utf-8"))
    prov = next((m for m in manifest if m["slug"] == SLUG), {})
    eff = prov.get("effective_date", "")
    if eff and len(eff) == 8:
        eff = f"{eff[:4]}-{eff[4:6]}-{eff[6:]}"
    url = prov.get("source_url", "")
    law_name = prov.get("name", "방송통신기자재등의 적합성평가에 관한 고시")

    # 기존 EMC 별표 산출물만 정리(법령 parse 결과는 보존)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for f in OUT_DIR.glob(f"{SLUG}_appx01_*.md"):
        f.unlink()

    colmap: dict | None = None
    ff: dict[int, str] = {}      # 컬럼 forward-fill (대분류 병합·페이지 경계 대응)
    items: list[dict] = []

    with pdfplumber.open(PDF_PATH) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                if not table:
                    continue
                hr = _header_rows(table)
                if hr:
                    colmap = _build_colmap(table[:hr])
                if colmap is None:
                    continue
                text_cols = colmap["name"] + (
                    [colmap["major"]] if colmap["major"] is not None else []
                ) + ([colmap["desc"]] if colmap["desc"] is not None else [])

                for row in table[hr:]:
                    if not row:
                        continue
                    for c in text_cols:
                        if c >= len(row):
                            continue
                        v = normalize_inline(row[c])
                        if not v:
                            continue
                        # 대분류 셀은 "가.","나." 형태일 때만 갱신 — ※ 안내문이나 연속행이
                        # 대분류를 덮어쓰지 않도록(직전의 진짜 대분류 유지)
                        if c == colmap["major"] and not _MAJOR_HEAD.match(v):
                            continue
                        ff[c] = v
                    code = normalize_inline(row[colmap["code"]]) if (
                        colmap["code"] is not None and colmap["code"] < len(row)) else ""
                    if not _CODE.match(code):
                        continue  # 품목 경계가 아닌 행(설명/분류 continuation)

                    name = ""
                    for c in colmap["name"]:
                        if ff.get(c):
                            name = ff[c]
                            break
                    name = _NUM_PREFIX.sub("", name).strip()
                    if not name:
                        continue
                    major = ff.get(colmap["major"], "") if colmap["major"] is not None else ""
                    major = re.split(r"[:：]", major, maxsplit=1)[0].strip()  # 대분류명만(정의 제거)
                    desc = normalize_inline(row[colmap["desc"]]) if (
                        colmap["desc"] is not None and colmap["desc"] < len(row)) else ""
                    certs = [label for i, label in colmap["cert"].items()
                             if i < len(row) and _has_circle(row[i])]
                    certs = [c for c in _CERT_ORDER if c in certs]

                    items.append({
                        "name": name, "major": major, "desc": desc,
                        "cert": "/".join(certs), "code": code,
                    })

    # 중복 기기부호 제거(같은 코드가 여러 행에 걸치는 경우 첫 건만)
    seen: set[str] = set()
    count = 0
    for seq, it in enumerate(items, start=1):
        if it["code"] in seen:
            continue
        seen.add(it["code"])
        meta = {
            "doc_type": "별표",
            "axis": "전자파",
            "category": "전기용품",
            "cert_level": it["cert"] or "적합성평가대상",
            "item_name": it["name"],
            "law_name": law_name,
            "article": "별표1 (적합성평가 대상기자재)",
            "effective_date": eff,
            "source_url": url,
        }
        body_lines = []
        if it["major"]:
            body_lines.append(f"분류: {it['major']}")
        body_lines.append(f"품목: {it['name']}")
        if it["desc"]:
            body_lines.append(it["desc"])
        body_lines.append(f"적합성평가 유형: {it['cert'] or '미상'} (기기부호 {it['code']})")
        body = clean_legal_text("\n".join(body_lines))

        lines = ["---"]
        for k, v in meta.items():
            if v:
                lines.append(f"{k}: {normalize_inline(v)}")
        lines += ["---", "", body, ""]
        (OUT_DIR / f"{SLUG}_appx01_{seq:03d}.md").write_text("\n".join(lines), encoding="utf-8")
        count += 1

    print(f"  [emc_conformity 별표1] {count}건 (전자파 품목)")


if __name__ == "__main__":
    main()
