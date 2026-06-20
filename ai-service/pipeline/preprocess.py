"""법령 본문 전처리 모듈.

ingest.py가 임베딩 직전에 이 모듈의 clean_legal_text()를 호출한다.
원문에 섞인 노이즈(개정 마커, 삭제 항목, 비표준 특수문자)를 제거하는 게 목적이다.

단독 실행으로 동작을 확인할 수 있다:
    uv run python preprocess.py
"""
from __future__ import annotations

import re
import unicodedata

# "<개정 2025. 10. 1.>", "<신설 ...>", "<시행일 ...>" 같은 인라인 마커 패턴
_REVISION_MARK = re.compile(r"<\s*(개정|신설|시행일|본조신설|제목개정|전문개정)[^>]*>")

# "1) 삭제 <2026. 4. 1.>", "가. 삭제 <...>" 처럼 통째로 삭제된 항목 '줄' 패턴
_DELETED_LINE = re.compile(r"^\s*(?:\d+\)|[가-힣]\.)\s*삭제\s*<[^>]*>\s*$")


def _normalize_chars(text: str) -> str:
    """문자 표기를 정규화한다."""
    text = unicodedata.normalize("NFC", text)         # 자모 분해(NFD) → 조합형(NFC)
    text = text.replace("\u3000", " ")             # 전각 공백 → 일반 공백
    text = text.replace("ㆍ", "·").replace("‧", "·")   # 가운뎃점 변종 → 표준 가운뎃점
    return text


def clean_legal_text(text: str) -> str:
    """법령 본문에서 검색 노이즈를 제거한다."""
    kept: list[str] = []
    for line in text.splitlines():
        if _DELETED_LINE.match(line):        # ① 삭제 항목 줄은 통째로 제거
            continue
        line = _REVISION_MARK.sub("", line)   # ② 인라인 <개정 ...> 마커 제거
        kept.append(line.rstrip())            # ③ 줄 끝 공백 제거
    text = "\n".join(kept)
    text = _normalize_chars(text)             # ④ 특수문자 정규화
    text = re.sub(r"\n{3,}", "\n\n", text)    # ⑤ 빈 줄 3개 이상이면 2개로 축소
    return text.strip()


# 직접 실행 시 샘플 before/after 출력 (동작 검증용)
if __name__ == "__main__":
    sample = (
        "제5조(안전인증 등) ① ... 안전인증을 받아야 한다. <개정 2025. 10. 1.>\n"
        "사. 전기기기:\n"
        "1) 삭제 <2026. 4. 1.>\n"
        "5) 모발관리기\n"
        "비고) 기계ㆍ기구에 부착되는 특수구조인 것은 제외한다."
    )
    print("===== BEFORE =====")
    print(sample)
    print("\n===== AFTER =====")
    print(clean_legal_text(sample))