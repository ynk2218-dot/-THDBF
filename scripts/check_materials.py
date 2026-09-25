"""자료 자동 검수: python scripts/check_materials.py <output 폴더>

사람(=Claude)이 쓴 자료를 기계적으로 점검할 수 있는 부분만 확인한다.
  1) 파일 6개가 모두 있는가
  2) 모든 타임스탬프가 강의 길이 안에 있고, 전사본(raw)의 실제 블록 시각과 맞는가
  3) 문제지: 문항 수·유형·난이도 비율이 설정과 같은가 / 문제지에 정답·타임스탬프가 새지 않았는가
  4) 해설: 모든 문항에 해설이 있고, 객관식 해설에 오답 원인 태그가 있는가
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402,F401  (출력 인코딩을 UTF-8 로 맞춤)

REQUIRED = ["01_정리본.md", "02_필기본.md", "03_필사본.md", "04_워크북.md", "05_문제지.md", "05_정답해설.md"]
TS = re.compile(r"\[((?:\d{1,2}:)?\d{1,2}:\d{2})(?:\s*[–~-]\s*((?:\d{1,2}:)?\d{1,2}:\d{2}))?\]")
TAGS = ["[개념 미이해]", "[적용 실패]", "[용어 혼동]", "[부주의]"]


def sec(ts: str) -> int:
    p = [int(x) for x in ts.split(":")]
    return p[-1] + p[-2] * 60 + (p[-3] * 3600 if len(p) == 3 else 0)


def main() -> int:
    out = Path(sys.argv[1]).expanduser().resolve()
    meta = json.loads((out / "_source/meta.json").read_text(encoding="utf-8"))
    dur = float(meta.get("duration_sec") or 0)
    raw = (out / "_source/transcript_raw.md").read_text(encoding="utf-8")
    starts = sorted({sec(m.group(1)) for m in re.finditer(r"^\[((?:\d+:)?\d+:\d{2})\]", raw, re.M)})
    errors, warns = [], []

    for name in REQUIRED:
        if not (out / name).exists():
            errors.append(f"{name} 없음")

    # ── 타임스탬프 ──
    for f in sorted(out.glob("[0-9][0-9]_*.md")) + [out / "analysis.md"]:
        if not f.exists():
            continue
        for ln, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            for m in TS.finditer(line):
                for i, g in enumerate(m.groups()):
                    if not g:
                        continue
                    s = sec(g)
                    if dur and s > dur + 1:
                        errors.append(f"{f.name}:{ln} {m.group(0)} — 강의 길이({int(dur)}초)를 넘음")
                    elif i == 0 and starts and s not in starts:
                        near = min(starts, key=lambda x: abs(x - s))
                        if abs(near - s) > 15:
                            warns.append(f"{f.name}:{ln} {m.group(0)} — 가장 가까운 전사 블록과 {abs(near - s)}초 차이")

    # ── 교재 쪽 번호 ──
    books = meta.get("textbook") or []
    max_page = max((b.get("pages") or 0 for b in books if b.get("kind") == "pdf"), default=0)
    for f in sorted(out.glob("[0-9][0-9]_*.md")) + [out / "analysis.md"]:
        if not f.exists():
            continue
        for ln, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            for m in re.finditer(r"\[교재 p\.?\s*(\d+)(?:\s*[–~-]\s*(\d+))?\]", line):
                if not books:
                    errors.append(f"{f.name}:{ln} {m.group(0)} — 교재를 받지 않았는데 교재 인용이 있음")
                elif max_page and int(m.group(2) or m.group(1)) > max_page:
                    errors.append(f"{f.name}:{ln} {m.group(0)} — 교재는 {max_page}쪽까지만 있음")
                elif f.name.startswith("05_문제지"):
                    warns.append(f"{f.name}:{ln} 문제지에 교재 쪽 표시 — 힌트가 되지 않는지 확인")

    # ── 문제지 ──
    exam_p, ans_p = out / "05_문제지.md", out / "05_정답해설.md"
    cfg = (meta.get("config") or {}).get("materials", {}).get("문제지", {})
    if exam_p.exists() and cfg:
        exam = exam_p.read_text(encoding="utf-8")
        heads = re.findall(r"^###\s*(\d+)\.\s*\[(기본|응용|심화)\](.*)$", exam, re.M)
        total = cfg.get("total")
        if len(heads) != total:
            errors.append(f"문제지 문항 수 {len(heads)} ≠ 설정 {total}")
        n_short = sum("(단답)" in h[2] for h in heads)
        n_essay = sum("(서술형)" in h[2] for h in heads)
        n_mc = len(heads) - n_short - n_essay
        want = cfg.get("types", {})
        got = {"객관식": n_mc, "단답": n_short, "서술형": n_essay}
        for k, v in want.items():
            if got.get(k) != v:
                errors.append(f"문제지 {k} {got.get(k)}문항 ≠ 설정 {v}")
        for lv, pct in (cfg.get("difficulty") or {}).items():
            cnt = sum(h[1] == lv for h in heads)
            expect = round(total * pct / 100)
            if abs(cnt - expect) > 1:
                errors.append(f"문제지 [{lv}] {cnt}문항 — 설정 비율 {pct}%(≈{expect}문항)과 다름")
        if TS.search(exam):
            errors.append("문제지에 타임스탬프가 있음 (힌트 유출)")
        if re.search(r"정답|해설", exam.split("\n", 1)[1] if "\n" in exam else ""):
            warns.append("문제지 본문에 '정답/해설'이라는 말이 있음 — 유출 여부 확인")

        if ans_p.exists():
            ans = ans_p.read_text(encoding="utf-8")
            blocks = re.split(r"^###\s*", ans, flags=re.M)[1:]
            got_nums = {int(re.match(r"(\d+)", b).group(1)) for b in blocks if re.match(r"\d+", b)}
            for num, lv, rest in heads:
                n = int(num)
                if n not in got_nums:
                    errors.append(f"해설에 {n}번 없음")
            mc_nums = {int(h[0]) for h in heads if "(단답)" not in h[2] and "(서술형)" not in h[2]}
            for b in blocks:
                m = re.match(r"(\d+)", b)
                if m and int(m.group(1)) in mc_nums and not any(t in b for t in TAGS):
                    errors.append(f"해설 {m.group(1)}번: 오답 원인 태그 없음")
                if m and not TS.search(b):
                    warns.append(f"해설 {m.group(1)}번: 근거 타임스탬프 없음")

    for w in warns:
        print(f"⚠️  {w}")
    for e in errors:
        print(f"❌ {e}")
    if not errors:
        print(f"✅ 검수 통과 (경고 {len(warns)}건)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
