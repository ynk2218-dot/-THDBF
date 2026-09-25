"""전사본 정제: 타임스탬프 유지본 / 읽기용 정제본 / 긴 강의 구간 분할."""
from __future__ import annotations

import re

from common import Segment, fmt_ts

SENT_END = re.compile(r"[.?!。？！]$|(다|요|죠|까|니다|습니다)[.]?$")


# ── 1) 세그먼트 → 블록 (타임스탬프 유지본용) ─────────
def group_blocks(segs: list[Segment], max_len: float = 20.0, min_len: float = 8.0) -> list[Segment]:
    """짧은 자막 조각을 약 8~20초 단위로 묶는다. 가능하면 문장 끝에서 끊는다."""
    blocks: list[Segment] = []
    cur: Segment | None = None
    for s in segs:
        if cur is None:
            cur = Segment(s.start, s.end, s.text)
            continue
        dur = s.end - cur.start
        ends_sentence = bool(SENT_END.search(cur.text))
        if dur > max_len or (cur.end - cur.start >= min_len and ends_sentence):
            blocks.append(cur)
            cur = Segment(s.start, s.end, s.text)
        else:
            cur.text = f"{cur.text} {s.text}"
            cur.end = s.end
    if cur:
        blocks.append(cur)
    return blocks


# ── 2) 말버릇·반복 정리 ──────────────────────────────
# 의미가 있을 수 있는 말("그", "이제", "좀")은 건드리지 않고,
# 명백한 간투사와 기계적 반복만 지운다. (강의 내용을 바꾸지 않는 것이 우선)
_FILLERS_KO = r"(?:음+|으+음*|어+|어어+|아+|에+|엄+|흠+)"
_FILLERS_EN = r"(?:um+|uh+|uhm+|erm+|hmm+|mm+|ah+)"
_NOISE = re.compile(r"\[(?:음악|박수|웃음|Music|Applause|Laughter|music|applause|laughter)\]|>>|♪+")
_FILLER_RE = re.compile(
    rf"(?<![\w가-힣])(?:{_FILLERS_KO}|{_FILLERS_EN})[,.…]*(?![\w가-힣])", re.IGNORECASE
)
_REPEAT_WORD = re.compile(r"\b(\w+)(?:\s+\1\b)+", re.IGNORECASE)          # the the / 이 이
_REPEAT_PHRASE = re.compile(r"((?:\S+\s+){1,3}?\S+)(?:\s+\1\b)+")          # 2~4어절 반복
# 한국어는 반복 뒤에 조사가 붙는 경우가 많다: "수요와 공급 수요와 공급에" → "수요와 공급에"
_REPEAT_KO = re.compile(r"(?<![가-힣])((?:[가-힣]+\s+){0,3}[가-힣]{2,})(?:\s+\1)+(?=[가-힣]{0,2}(?:[\s,.?!]|$))")


def guess_language(segs: list[Segment]) -> str:
    sample = "".join(s.text for s in segs[:200])
    hangul = len(re.findall(r"[가-힣]", sample))
    latin = len(re.findall(r"[A-Za-z]", sample))
    return "ko" if hangul >= latin else "en"


def clean_text(text: str) -> str:
    t = _NOISE.sub(" ", text)
    t = _FILLER_RE.sub(" ", t)
    t = _REPEAT_PHRASE.sub(r"\1", t)
    t = _REPEAT_KO.sub(r"\1", t)
    t = _REPEAT_WORD.sub(r"\1", t)
    t = re.sub(r"\s+([,.?!])", r"\1", t)
    t = re.sub(r"([,.?!]){2,}", r"\1", t)
    t = re.sub(r"^[,.\s]+", "", t)
    return re.sub(r"\s{2,}", " ", t).strip()


# ── 3) 출력 ──────────────────────────────────────────
def render_raw(blocks: list[Segment], title: str, hours: bool) -> str:
    lines = [f"# 전사본 (타임스탬프 유지) — {title}", ""]
    for b in blocks:
        lines.append(f"[{fmt_ts(b.start, hours)}] {b.text}")
        lines.append("")
    return "\n".join(lines)


def render_clean(blocks: list[Segment], title: str, hours: bool, para_len: float = 75.0) -> str:
    """약 1분 남짓 단위 문단. 문단 맨 앞에만 타임스탬프를 달아 읽기 쉽게."""
    lines = [
        f"# 전사본 (읽기용 정제본) — {title}",
        "",
        "> 말버릇(음, 어, um, uh)과 기계적 반복만 지웠습니다. 표현은 강사 발화를 그대로 두었습니다.",
        "",
    ]
    para: list[str] = []
    para_start = None
    for b in blocks:
        t = clean_text(b.text)
        if not t:
            continue
        if para_start is None:
            para_start = b.start
        para.append(t)
        if b.end - para_start >= para_len and SENT_END.search(t):
            lines += [f"**[{fmt_ts(para_start, hours)}]** " + " ".join(para), ""]
            para, para_start = [], None
    if para:
        lines += [f"**[{fmt_ts(para_start, hours)}]** " + " ".join(para), ""]
    return "\n".join(lines)


def split_chunks(blocks: list[Segment], chunk_sec: float) -> list[list[Segment]]:
    """목표 길이를 넘긴 뒤 처음 나오는 문장 끝에서 자른다(최대 2분 여유)."""
    chunks, cur = [], []
    start = blocks[0].start if blocks else 0
    for b in blocks:
        cur.append(b)
        elapsed = b.end - start
        if elapsed >= chunk_sec and (SENT_END.search(b.text) or elapsed >= chunk_sec + 120):
            chunks.append(cur)
            cur = []
            start = b.end
    if cur:
        # 마지막 조각이 너무 짧으면(3분 미만) 앞 구간에 붙인다
        if chunks and cur[-1].end - cur[0].start < 180:
            chunks[-1].extend(cur)
        else:
            chunks.append(cur)
    return chunks
