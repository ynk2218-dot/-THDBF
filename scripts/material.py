"""교재(보조 자료) 준비: --material 로 받은 파일을 _source/materials/ 에 모으고 글자를 뽑는다.

- PDF        → 쪽마다 글자 추출해 material.md 에 `## [교재 p.N]` 로 기록
               (글자가 거의 없는 스캔본이면 Claude 가 PDF 를 직접 '보고' 읽도록 표시)
- 이미지      → 판서·교재 사진. Claude 가 직접 보고 읽음
- txt / md   → 그대로 옮김
- hwp, docx 등 → 지원하지 않음: PDF 로 저장해서 넣도록 안내
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from common import StudyError, log, warn

PDF_EXTS = {".pdf"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
TEXT_EXTS = {".txt", ".md"}
MIN_CHARS_PER_PAGE = 30   # 이보다 글자가 적은 쪽은 스캔(그림)으로 본다


def _extract_pdf(path: Path) -> tuple[list[tuple[int, str]], int]:
    """(글자가 있는 쪽 목록, 전체 쪽 수). pypdf 가 없으면 빈 목록."""
    try:
        from pypdf import PdfReader
    except BaseException:  # 미설치(ImportError)뿐 아니라 의존 라이브러리 충돌(panic)도 여기서 흡수
        warn("PDF 글자 추출 도구(pypdf)를 쓸 수 없어, Claude 가 PDF 를 직접 읽습니다.")
        return [], 0
    try:
        reader = PdfReader(str(path))
    except Exception as e:
        raise StudyError("INPUT_NOT_FOUND", f"교재 PDF를 열 수 없습니다: {path.name}",
                         fix="암호가 걸린 PDF라면 암호를 풀어 다시 저장한 뒤 넣어 주세요.", detail=repr(e)) from None
    pages = []
    for i, page in enumerate(reader.pages, 1):
        try:
            text = (page.extract_text() or "").strip()
        except Exception:
            text = ""
        text = re.sub(r"[ \t]{2,}", " ", text)           # 한글 PDF 에서 흔한 이중 공백
        text = re.sub(r" +([.,?!)])", r"\1", text)
        pages.append((i, text))
    return pages, len(reader.pages)


def prepare(paths: list[str], work: Path) -> list[dict]:
    """교재 파일을 복사·추출하고 meta 에 넣을 목록을 돌려준다."""
    if not paths:
        return []
    mdir = work / "materials"
    mdir.mkdir(exist_ok=True)
    out_md = ["# 교재 (보조 자료)", "",
              "> 강의에서 화면으로만 보여 준 문제·예문·표를 채우는 데 쓰는 자료입니다.",
              "> 인용 표기: `[교재 p.N]` (PDF 쪽 번호 기준)", ""]
    items = []
    for raw in paths:
        p = Path(raw.strip().strip('"').strip("'")).expanduser()
        if not p.exists():
            raise StudyError("INPUT_NOT_FOUND", f"교재 파일을 찾을 수 없습니다: {p}",
                             fix='경로에 오타가 없는지 확인하고, 공백이 있으면 "따옴표"로 감싸 주세요.')
        ext = p.suffix.lower()
        dst = mdir / p.name
        shutil.copy2(p, dst)
        item = {"file": f"_source/materials/{p.name}", "name": p.name}

        if ext in PDF_EXTS:
            pages, total = _extract_pdf(dst)
            texty = [(n, t) for n, t in pages if len(t) >= MIN_CHARS_PER_PAGE]
            item.update(kind="pdf", pages=total, text_pages=len(texty))
            if texty:
                out_md += [f"# {p.name}", ""]
                for n, t in texty:
                    out_md += [f"## [교재 p.{n}]", "", t, ""]
            scanned = total and len(texty) < total * 0.5
            item["read_directly"] = bool(scanned or not pages)
            if not pages:
                log(f"   📘 {p.name}: 글자를 미리 뽑지 못함 — Claude 가 PDF 를 직접 읽습니다")
            else:
                log(f"   📘 {p.name}: {total}쪽 중 {len(texty)}쪽에서 글자 추출"
                    + (" — 스캔본으로 보여 Claude 가 직접 읽습니다" if item["read_directly"] else ""))
        elif ext in IMAGE_EXTS:
            item.update(kind="image", read_directly=True)
            log(f"   🖼  {p.name}: 사진 — Claude 가 직접 보고 읽습니다")
        elif ext in TEXT_EXTS:
            item.update(kind="text", read_directly=False)
            out_md += [f"# {p.name}", "", dst.read_text(encoding="utf-8", errors="replace"), ""]
            log(f"   📄 {p.name}: 텍스트")
        else:
            raise StudyError(
                "INPUT_NOT_FOUND", f"교재 형식({ext})은 지원하지 않습니다: {p.name}",
                fix="한글(hwp)·워드(docx) 파일은 '다른 이름으로 저장 → PDF'로 바꿔서 넣어 주세요. "
                    "지원 형식: PDF, 사진(jpg/png), txt/md",
            )
        items.append(item)

    (work / "material.md").write_text("\n".join(out_md), encoding="utf-8")
    return items
