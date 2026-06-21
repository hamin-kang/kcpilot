"""raw 법령 JSON(data/raw/law_api/*.json)을 전처리·청킹해 data/processed/*.md로 변환한다.

설계 원칙:
- raw는 불변. 이 스크립트는 raw를 읽어 processed를 매번 새로 만든다(재실행 시 processed 비우고 재생성).
- 조문은 조문 1개 = 파일 1개. 의미 경계가 자연스럽다.
- 품목 분류 별표(안전 별표3~6, 어린이 별표1~3)는 품목 1개 = 파일 1개로 쪼갠다.
  통째로 임베딩하면 수십 개 품목이 섞여 검색이 희석되기 때문(data_pipeline.md §1-4).
- EMC 고시 별표1(전자파 품목)은 JSON ASCII표가 복잡해 PDF로 따로 파싱한다 → parse_emc_pdf.py.
- 본문은 임베딩 전에 clean_legal_text()로 노이즈를 제거한다.

실행:
    uv run python pipeline/parse_laws.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))

from preprocess import clean_legal_text, normalize_inline  # noqa: E402

RAW_DIR = ROOT / "data" / "raw" / "law_api"
OUT_DIR = ROOT / "data" / "processed"

# slug → 축/카테고리/문서종류. 분류 별표 품목은 섹션 헤더로 category를 다시 덮어쓴다.
SLUG_META: dict[str, dict] = {
    "safety_act":      {"axis": "안전", "category": "전기용품,생활용품", "doc_type": "법률"},
    "safety_decree":   {"axis": "안전", "category": "전기용품,생활용품", "doc_type": "시행령"},
    "safety_rule":     {"axis": "안전", "category": "전기용품,생활용품", "doc_type": "시행규칙"},
    "children_act":    {"axis": "안전", "category": "어린이제품", "doc_type": "법률"},
    "children_decree": {"axis": "안전", "category": "어린이제품", "doc_type": "시행령"},
    "children_rule":   {"axis": "안전", "category": "어린이제품", "doc_type": "시행규칙"},
    "wave_act":        {"axis": "전자파", "category": "전기용품", "doc_type": "법률"},
    "wave_decree":     {"axis": "전자파", "category": "전기용품", "doc_type": "시행령"},
    "wave_rule":       {"axis": "전자파", "category": "전기용품", "doc_type": "시행규칙"},
    "emc_conformity":  {"axis": "전자파", "category": "전기용품", "doc_type": "고시"},
}

# (slug, 별표번호) → {cert_level, mode}. mode: 'right'=우열에 품목, 'left'=좌열에 품목.
CLASSIFICATION_APPENDICES: dict[tuple[str, str], dict] = {
    ("safety_rule", "0003"): {"cert_level": "안전인증", "mode": "right"},
    ("safety_rule", "0004"): {"cert_level": "안전확인", "mode": "right"},
    ("safety_rule", "0005"): {"cert_level": "공급자적합성확인", "mode": "right"},
    ("safety_rule", "0006"): {"cert_level": "안전기준준수", "mode": "right"},
    ("children_rule", "0001"): {"cert_level": "안전인증", "mode": "left"},
    ("children_rule", "0002"): {"cert_level": "안전확인", "mode": "left"},
    ("children_rule", "0003"): {"cert_level": "공급자적합성확인", "mode": "left"},
}

# box-drawing 구분선(가로줄) 판별
_BORDER_CHARS = set("─━┄┈┌┐└┘├┤┬┴┼╔╗╚╝═║│ ")

_SECTION_HEADER = re.compile(r"^\s*\d+\.\s*(.+)$")
_NUM_ITEM = re.compile(r"^(\d+)\)\s*(.*)$")        # "5) 모발관리기"
_LEFT_ITEM = re.compile(r"^(?:\d+|[가-힣])\.\s*(.+)$")  # "1. 물놀이기구" / "가. 가죽제품"
_CLASS_HEAD = re.compile(r"^[가-힣]\.")             # "가. 전선 및 전원"
_ARTICLE_NO = re.compile(r"^제\s*(\d+)\s*조(?:의\s*(\d+))?")  # 제2조 / 제2조의2
_EMPTY_ITEM = re.compile(r"^(대상|해당)\s*없음$")  # "대상 없음"은 품목이 아님


# ---------- 공통 유틸 ----------
def _skip_item(name: str) -> bool:
    name = name.strip()
    return (not name) or ("삭제" in name) or bool(_EMPTY_ITEM.match(name))


def _fmt_date(yyyymmdd: str | None) -> str:
    if yyyymmdd and len(yyyymmdd) == 8 and yyyymmdd.isdigit():
        return f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:]}"
    return yyyymmdd or ""


def _as_list(x) -> list:
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


def _write_md(fname: str, meta: dict, body: str) -> bool:
    """frontmatter + 본문을 .md로 저장. 본문이 정제 후 비면 쓰지 않고 False를 반환한다."""
    body = clean_legal_text(body)
    if not body:
        return False
    lines = ["---"]
    for k, v in meta.items():
        if v is None or v == "":
            continue
        lines.append(f"{k}: {normalize_inline(v)}")
    lines.append("---")
    lines.append("")
    lines.append(body)
    (OUT_DIR / fname).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def _is_border(cell: str) -> bool:
    return bool(cell) and all(ch in _BORDER_CHARS for ch in cell)


def _split_cells(line: str) -> list[str] | None:
    """'│좌│우│' → ['좌','우']. 표 행이 아니면 None."""
    if "│" not in line:
        return None
    parts = line.split("│")
    cells = [c.strip() for c in parts[1:-1]]  # 양끝 테두리 밖 제거
    if len(cells) < 2:
        return None
    return cells


# ---------- 분류 별표 파서 ----------
def _parse_right_mode(lines: list[str]) -> list[dict]:
    """안전 별표(우열에 품목). 좌열=분류, 우열=N) 품목 / 단일품목 / 비고)."""
    classes: list[dict] = []     # 등장 순서 보존(디버그용)
    items: list[dict] = []
    cat: str | None = None
    cur_class: dict | None = None
    cur_item: dict | None = None
    state: str | None = None     # 'item' | 'note'

    for line in lines:
        # 섹션 헤더: "1. 안전인증대상전기용품" → category
        sec = _SECTION_HEADER.match(line.strip())
        if sec and "│" not in line:
            title = sec.group(1)
            if "생활용품" in title:
                cat = "생활용품"
            elif "어린이" in title:
                cat = "어린이제품"
            elif "전기용품" in title:
                cat = "전기용품"
            cur_class = None
            cur_item = None
            state = None
            continue

        cells = _split_cells(line)
        if cells is None:
            continue
        left, right = cells[0], cells[1]
        if _is_border(left) and _is_border(right):
            continue
        if left in ("분류",) and right in ("품목",):  # 헤더행
            continue

        # 좌열: 분류 시작/word-wrap
        if _CLASS_HEAD.match(left):
            cur_class = {"name": left, "cat": cat, "note": ""}
            classes.append(cur_class)
            cur_item = None
            state = None
        elif left and not left[0].isdigit() and not _is_border(left) and cur_class:
            cur_class["name"] += left  # 분류명 word-wrap

        if not right or _is_border(right) or cur_class is None:
            continue

        if right.startswith("비고"):
            cur_class["note"] += (" " if cur_class["note"] else "") + right
            state = "note"
            cur_item = None
            continue

        m = _NUM_ITEM.match(right)
        if m:
            name = m.group(2).strip()
            if _skip_item(name):
                cur_item = None
                state = None
                continue
            cur_item = {"cls": cur_class, "name": name}
            items.append(cur_item)
            state = "item"
        else:
            # 번호 없는 우열 텍스트 (공백 없이 이어붙임 — 한글 줄바꿈)
            if state == "note":
                cur_class["note"] += right
            elif state == "item" and cur_item:
                cur_item["name"] += right
            elif not _skip_item(right):
                cur_item = {"cls": cur_class, "name": right}  # 분류의 단일 품목
                items.append(cur_item)
                state = "item"
    return items


def _parse_left_mode(lines: list[str]) -> list[dict]:
    """어린이 별표(좌열에 품목). 좌열=N. 품목, 우열=적용 안전기준."""
    items: list[dict] = []
    cur: dict | None = None
    for line in lines:
        cells = _split_cells(line)
        if cells is None:
            continue
        left, right = cells[0], cells[1]
        if _is_border(left) and _is_border(right):
            continue
        if right in ("적용 안전기준", "적용 안전 기준") or left.endswith("어린이제품"):
            continue  # 헤더행

        m = _LEFT_ITEM.match(left)
        if m:
            name = m.group(1).strip()
            if _skip_item(name):          # "나. 삭제 <...>" 등은 제외
                cur = None
                continue
            cur = {"name": name, "applies": [], "cat": "어린이제품", "note": ""}
            items.append(cur)
            if right and not _is_border(right):
                cur["applies"].append(right)
        elif cur is not None:
            if left and not _is_border(left):
                cur["name"] += left  # 품목명 word-wrap (공백 없이)
            if right and not _is_border(right):
                cur["applies"].append(right)
    return items


def _item_body_right(item: dict) -> str:
    cls = item["cls"]
    cat = cls.get("cat") or ""
    head = f"{cat} - {cls['name']}" if cat else cls["name"]
    body = f"{head}: {item['name']}"
    if cls.get("note"):
        body += "\n" + cls["note"]
    return body


def _item_body_left(item: dict) -> str:
    body = f"어린이제품: {item['name']}"
    if item["applies"]:
        body += "\n적용 안전기준: " + " / ".join(item["applies"])
    return body


# ---------- 법령(법령 키) 처리 ----------
def process_law(slug: str, data: dict, prov: dict) -> int:
    meta_base = SLUG_META[slug]
    law_name = data["법령"]["기본정보"].get("법령명_한글", prov.get("name", slug))
    eff = _fmt_date(prov.get("effective_date"))
    url = prov.get("source_url", "")
    count = 0

    # --- 조문 ---
    for u in _as_list(data["법령"].get("조문", {}).get("조문단위")):
        if u.get("조문여부") != "조문":
            continue
        content = u.get("조문내용") or ""
        if not content.strip():
            continue
        no = u.get("조문번호", "")
        branch = u.get("조문가지번호") or ""
        if branch in ("00", "0"):
            branch = ""
        jo = f"제{no}조" + (f"의{int(branch)}" if branch.isdigit() else "")
        title = u.get("조문제목") or ""
        article = f"{jo}({title})" if title else jo
        meta = {
            "doc_type": meta_base["doc_type"],
            "axis": meta_base["axis"],
            "category": meta_base["category"],
            "law_name": law_name,
            "article": article,
            "effective_date": _fmt_date(u.get("조문시행일자")) or eff,
            "source_url": url,
        }
        no_safe = re.sub(r"\D", "_", no).zfill(3)
        suffix = f"_{int(branch)}" if branch.isdigit() else ""
        if _write_md(f"{slug}_art{no_safe}{suffix}.md", meta, content):
            count += 1

    # --- 별표 ---
    for u in _as_list(data["법령"].get("별표", {}).get("별표단위")):
        if u.get("별표구분") != "별표":
            continue
        num = u.get("별표번호", "")
        title = u.get("별표제목", "")
        lines = u.get("별표내용") or []
        lines = lines[0] if lines and isinstance(lines[0], list) else lines
        if not lines:
            continue

        cfg = CLASSIFICATION_APPENDICES.get((slug, num))
        if not cfg:
            # 품목 분류표가 아닌 별표(보고·검사 항목, 표시기준, 행정처분, 수수료·과태료,
            # 서식 등)는 KC 진단 검색에 가치가 없고 ASCII 박스 노이즈만 더한다 → 제외.
            continue

        parser = _parse_right_mode if cfg["mode"] == "right" else _parse_left_mode
        for seq, item in enumerate(parser(lines), start=1):
            cat = (item.get("cls") or item).get("cat") or meta_base["category"]
            meta = {
                "doc_type": "별표",
                "axis": meta_base["axis"],
                "category": cat,
                "cert_level": cfg["cert_level"],
                "item_name": item["name"].strip(),
                "law_name": law_name,
                "article": f"별표{int(num)} ({title.split('(')[0].strip()})",
                "effective_date": eff,
                "source_url": url,
            }
            body = _item_body_right(item) if cfg["mode"] == "right" else _item_body_left(item)
            if _write_md(f"{slug}_appx{int(num):02d}_{seq:03d}.md", meta, body):
                count += 1

    return count


# ---------- 행정규칙(AdmRulService 키) 처리: 조문만 ----------
def process_admrul(slug: str, data: dict, prov: dict) -> int:
    meta_base = SLUG_META[slug]
    svc = data["AdmRulService"]
    name = svc.get("행정규칙기본정보", {}).get("행정규칙명", prov.get("name", slug))
    eff = _fmt_date(prov.get("effective_date"))
    url = prov.get("source_url", "")
    count = 0
    for chunk in _as_list(svc.get("조문내용")):
        text = chunk if isinstance(chunk, str) else " ".join(_as_list(chunk))
        text = text.strip()
        m = _ARTICLE_NO.match(text)
        if not m:
            continue  # 장 제목("제1장 총칙") 등은 스킵
        no, branch = m.group(1), m.group(2)
        jo = f"제{no}조" + (f"의{branch}" if branch else "")
        meta = {
            "doc_type": meta_base["doc_type"],
            "axis": meta_base["axis"],
            "category": meta_base["category"],
            "law_name": name,
            "article": jo,
            "effective_date": eff,
            "source_url": url,
        }
        suffix = f"_{int(branch)}" if branch else ""
        if _write_md(f"{slug}_art{no.zfill(3)}{suffix}.md", meta, text):
            count += 1
    return count


def main() -> None:
    manifest = json.loads((RAW_DIR / "_manifest.json").read_text(encoding="utf-8"))
    prov_by_slug = {m["slug"]: m for m in manifest}

    if OUT_DIR.exists():
        for f in OUT_DIR.glob("*.md"):
            f.unlink()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    total = 0
    for slug, meta in SLUG_META.items():
        path = RAW_DIR / f"{slug}.json"
        if not path.exists():
            print(f"  (없음, 건너뜀: {slug}.json)")
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        prov = prov_by_slug.get(slug, {})
        if "법령" in data:
            n = process_law(slug, data, prov)
        elif "AdmRulService" in data:
            n = process_admrul(slug, data, prov)
        else:
            print(f"  (알 수 없는 구조: {slug})")
            continue
        print(f"  [{slug}] {n}건")
        total += n

    print(f"\n완료. data/processed/에 {total}건 생성. (EMC 별표1은 parse_emc_pdf.py로 별도 생성)")


if __name__ == "__main__":
    main()
