"""Markdown 학습 자료 → 인쇄용 PDF (A4, 한글 Noto Sans KR, 문제지는 2단).

사용법:
    python scripts/render_pdf.py <output 폴더> [파일명.md ...]

Markdown 확장 문법 (자료 작성 가이드와 짝을 이룸):
    ::: 이름  …  :::       → <div class="이름"> (중첩 가능: cornell / cue / note / summary / card / q …)
    ```mermaid            → 개념 관계도 그림
    ______ (한 줄 전체)    → 필기용 밑줄 한 줄
    (_____) (문장 속)      → 빈칸
    [03:12]               → 유튜브 강의면 해당 시점으로 가는 링크
    [보충] [기본] [응용] [심화] [개념 미이해] 등 → 색 배지
"""
from __future__ import annotations

import glob
import html
import io
import json
import os
import re
import sys
import tarfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, load_config, log, warn  # noqa: E402

import markdown  # noqa: E402

TEMPLATES = ROOT / "templates"
FONT_PATH = TEMPLATES / "fonts" / "NotoSansKR.ttf"
MERMAID_PATH = TEMPLATES / "vendor" / "mermaid.min.js"
MERMAID_VER = "11.4.1"

FONT_URLS = [
    "https://raw.githubusercontent.com/google/fonts/main/ofl/notosanskr/NotoSansKR%5Bwght%5D.ttf",
    "https://github.com/google/fonts/raw/main/ofl/notosanskr/NotoSansKR%5Bwght%5D.ttf",
]
MERMAID_URLS = [
    f"https://cdn.jsdelivr.net/npm/mermaid@{MERMAID_VER}/dist/mermaid.min.js",
    f"https://unpkg.com/mermaid@{MERMAID_VER}/dist/mermaid.min.js",
    f"npm:https://registry.npmjs.org/mermaid/-/mermaid-{MERMAID_VER}.tgz",
]


# ── 에셋 (처음 한 번만 내려받아 templates/ 에 저장) ───────
def _download(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "study-materials/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def ensure_font() -> bool:
    if FONT_PATH.exists() and FONT_PATH.stat().st_size > 100_000:
        return True
    FONT_PATH.parent.mkdir(parents=True, exist_ok=True)
    for url in FONT_URLS:
        try:
            log("   한글 폰트(Noto Sans KR) 내려받는 중… (처음 한 번만)")
            data = _download(url)
            if len(data) > 100_000:
                FONT_PATH.write_bytes(data)
                return True
        except Exception:
            continue
    warn("Noto Sans KR 폰트를 받지 못해 컴퓨터에 있는 한글 폰트로 대신합니다.")
    return False


def ensure_mermaid() -> bool:
    if MERMAID_PATH.exists() and MERMAID_PATH.stat().st_size > 100_000:
        return True
    MERMAID_PATH.parent.mkdir(parents=True, exist_ok=True)
    for url in MERMAID_URLS:
        try:
            if url.startswith("npm:"):
                tgz = _download(url[4:])
                with tarfile.open(fileobj=io.BytesIO(tgz)) as tf:
                    data = tf.extractfile("package/dist/mermaid.min.js").read()
            else:
                data = _download(url)
            if len(data) > 100_000:
                MERMAID_PATH.write_bytes(data)
                return True
        except Exception:
            continue
    warn("개념 관계도(mermaid) 도구를 받지 못해, PDF에는 관계도 원문 텍스트가 대신 들어갑니다.")
    return False


# ── Markdown → HTML ──────────────────────────────────
MD_EXT = ["tables", "fenced_code", "sane_lists", "attr_list", "def_list", "md_in_html"]
_MAT_RE = re.compile(r"\[(교재[^\]\n]{0,40})\]")
_LIST_RE = re.compile(r"^\s*(?:[-*+]|\d+\.)\s")
_TS_RE = re.compile(r"\[((?:\d{1,2}:)?\d{1,2}:\d{2})((?:\s*[–~-]\s*(?:\d{1,2}:)?\d{1,2}:\d{2})?)\]")
_BADGES = {
    "보충": "supp", "기본": "lv lv1", "응용": "lv lv2", "심화": "lv lv3",
    "확인 불가": "unk",
    "개념 미이해": "tag", "적용 실패": "tag", "용어 혼동": "tag", "부주의": "tag",
}


class Converter:
    def __init__(self, ts_url: str | None):
        self.ts_url = ts_url
        self.mermaid: list[str] = []
        self.raw: list[str] = []

    def _stash(self, html_str: str) -> str:
        self.raw.append(html_str)
        return f"\n\nRAWHTML{len(self.raw) - 1}END\n\n"

    def _prep(self, text: str) -> str:
        """코드블록 밖의 밑줄·mermaid 를 먼저 치환 (markdown 이 굵게/가로줄로 오해하지 않게)."""
        out, in_code, fence, buf = [], False, "", []
        for line in text.split("\n"):
            s = line.strip()
            if not in_code and s.startswith("```mermaid"):
                in_code, fence, buf = True, "mermaid", []
                continue
            if in_code and fence == "mermaid":
                if s.startswith("```"):
                    src = "\n".join(buf)
                    self.mermaid.append(src)
                    out.append(self._stash(
                        f'<figure class="diagram"><div class="mermaid">{html.escape(src)}</div>'
                        f'<pre class="mermaid-src">{html.escape(src)}</pre></figure>'))
                    in_code, fence = False, ""
                else:
                    buf.append(line)
                continue
            if s.startswith("```"):
                in_code = not in_code
                out.append(line)
                continue
            if in_code:
                out.append(line)
                continue
            if re.fullmatch(r"_{5,}", s):
                out.append(self._stash('<div class="rule"></div>'))
                continue
            line = re.sub(r"_{3,}", '<span class="blank"></span>', line)
            # python-markdown 은 목록 앞에 빈 줄이 없으면 목록으로 인식하지 못한다(GitHub 은 인식).
            prev = out[-1] if out else ""
            if _LIST_RE.match(line) and prev.strip() and not _LIST_RE.match(prev) and not prev.startswith((" ", "\t", "|")):
                out.append("")
            out.append(line)
        return "\n".join(out)

    def _md(self, text: str) -> str:
        return markdown.markdown(self._prep(text), extensions=MD_EXT, output_format="html5")

    def _tree(self, text: str) -> list:
        """'::: 이름' 블록을 트리로 파싱."""
        root: list = []
        stack = [root]
        buf: list[str] = []
        in_code = False

        def flush():
            if buf:
                stack[-1].append(("md", "\n".join(buf)))
                buf.clear()

        for line in text.split("\n"):
            s = line.strip()
            if s.startswith("```"):
                in_code = not in_code
            if not in_code:
                m = re.match(r"^:::\s*([\w가-힣-]+)\s*(.*)$", s)
                if m and not s.endswith(":::"):
                    flush()
                    node: list = []
                    stack[-1].append(("div", m.group(1), m.group(2).strip(), node))
                    stack.append(node)
                    continue
                if s == ":::" and len(stack) > 1:
                    flush()
                    stack.pop()
                    continue
            buf.append(line)
        flush()
        return root

    def _render(self, nodes: list) -> str:
        parts = []
        for n in nodes:
            if n[0] == "md":
                parts.append(self._md(n[1]))
            else:
                _, cls, label, children = n
                lab = f'<div class="label">{html.escape(label)}</div>' if label else ""
                parts.append(f'<div class="{html.escape(cls)}">{lab}{self._render(children)}</div>')
        return "\n".join(parts)

    def convert(self, text: str) -> str:
        body = self._render(self._tree(text))
        body = re.sub(r"<p>\s*RAWHTML(\d+)END\s*</p>|RAWHTML(\d+)END",
                      lambda m: f"%%RAW{m.group(1) or m.group(2)}%%", body)
        body = self._inline(body)
        return re.sub(r"%%RAW(\d+)%%", lambda m: self.raw[int(m.group(1))], body)

    def _inline(self, body: str) -> str:
        # 체크박스
        body = re.sub(r"<li>\s*\[ \]\s*", '<li class="check">☐ ', body)
        body = re.sub(r"<li>\s*\[[xX]\]\s*", '<li class="check">☑ ', body)
        # 배지
        for word, cls in _BADGES.items():
            body = body.replace(f"[{word}]", f'<span class="badge {cls}">{word}</span>')
        body = _MAT_RE.sub(lambda m: f'<span class="badge mat">{m.group(1)}</span>', body)
        # 타임스탬프 → 링크
        def ts(m: re.Match) -> str:
            label = m.group(0)
            if not self.ts_url:
                return f'<span class="ts">{label}</span>'
            parts = [int(x) for x in m.group(1).split(":")]
            sec = parts[-1] + parts[-2] * 60 + (parts[-3] * 3600 if len(parts) == 3 else 0)
            return f'<a class="ts" href="{self.ts_url.format(sec=sec)}">{label}</a>'
        # 코드/pre 안은 건드리지 않기
        chunks = re.split(r"(<pre.*?</pre>|<code.*?</code>)", body, flags=re.S)
        return "".join(c if c.startswith(("<pre", "<code")) else _TS_RE.sub(ts, c) for c in chunks)


# ── HTML 문서 조립 ───────────────────────────────────
def doc_kind(name: str) -> str:
    if name.startswith("05_문제지"):
        return "exam"
    if name.startswith("02_"):
        return "cornell"
    return "base"


def build_html(md_text: str, title: str, kind: str, ts_url: str | None, has_font: bool, has_mermaid: bool) -> str:
    conv = Converter(ts_url)
    body = conv.convert(md_text)
    css = (TEMPLATES / "base.css").read_text(encoding="utf-8")
    extra = TEMPLATES / f"{kind}.css"
    if kind != "base" and extra.exists():
        css += "\n" + extra.read_text(encoding="utf-8")
    font_face = ""
    if has_font:
        font_face = (
            "@font-face{font-family:'Noto Sans KR';src:url('%s') format('truetype');"
            "font-weight:100 900;font-style:normal;}" % FONT_PATH.as_uri()
        )
    script = ""
    if conv.mermaid and has_mermaid:
        script = f"""
<script src="{MERMAID_PATH.as_uri()}"></script>
<script>
  window.__done = false;
  mermaid.initialize({{startOnLoad:false, theme:'neutral', fontFamily:"'Noto Sans KR', sans-serif",
                      suppressErrorRendering:true, flowchart:{{htmlLabels:false, curve:'basis'}}}});
  mermaid.run({{querySelector:'.mermaid'}})
    .catch(() => {{}})
    .finally(() => {{
      document.querySelectorAll('figure.diagram').forEach(f => {{
        if (!f.querySelector('svg')) f.classList.add('failed');
      }});
      window.__done = true;
    }});
</script>"""
    elif conv.mermaid:
        body = body.replace('<figure class="diagram">', '<figure class="diagram failed">')
    if not script:
        script = "<script>window.__done = true;</script>"
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>{font_face}
{css}</style></head>
<body class="doc-{kind}"><main class="content">
{body}
</main>{script}</body></html>"""


# ── 브라우저 (PDF 인쇄) ───────────────────────────────
def _launch(p, cfg: dict):
    tried = []
    custom = ((cfg.get("pdf") or {}).get("chromium_path") or os.environ.get("STUDY_CHROMIUM_PATH") or "").strip()
    attempts = []
    if custom:
        attempts.append(("경로 지정", {"executable_path": custom}))
    attempts.append(("Playwright 기본", {}))
    attempts += [("설치된 Chrome", {"channel": "chrome"}), ("설치된 Edge", {"channel": "msedge"})]
    bp = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if bp:
        for exe in sorted(glob.glob(os.path.join(bp, "chromium-*", "chrome-*", "chrome")), reverse=True):
            attempts.append(("Playwright 폴더", {"executable_path": exe}))
    for label, kw in attempts:
        try:
            return p.chromium.launch(**kw)
        except Exception as e:
            tried.append(f"{label}: {str(e).splitlines()[0][:120]}")
    raise RuntimeError(
        "PDF를 만들 브라우저를 찾지 못했습니다. 터미널에서  python -m playwright install chromium  을 "
        "실행한 뒤 다시 시도하세요.\n  시도한 방법:\n  - " + "\n  - ".join(tried))


FOOTER = ('<div style="width:100%;font-size:8px;color:#999;text-align:center;">'
          '<span class="pageNumber"></span> / <span class="totalPages"></span></div>')


def render(out_dir: Path, names: list[str] | None = None) -> list[Path]:
    from playwright.sync_api import sync_playwright

    cfg = load_config()
    meta_p = out_dir / "_source" / "meta.json"
    meta = json.loads(meta_p.read_text(encoding="utf-8")) if meta_p.exists() else {}
    ts_url = meta.get("ts_url")
    files = [out_dir / n for n in names] if names else sorted(out_dir.glob("[0-9][0-9]_*.md"))
    if not files:
        raise SystemExit(f"변환할 자료(01_…md)가 없습니다: {out_dir}")
    has_font = ensure_font()
    need_mermaid = any("```mermaid" in f.read_text(encoding="utf-8") for f in files)
    has_mermaid = ensure_mermaid() if need_mermaid else False

    html_dir = out_dir / "_source" / "html"
    html_dir.mkdir(parents=True, exist_ok=True)
    made = []
    with sync_playwright() as p:
        browser = _launch(p, cfg)
        page = browser.new_page()
        for f in files:
            kind = doc_kind(f.name)
            doc = build_html(f.read_text(encoding="utf-8"), f"{f.stem} — {meta.get('title', '')}",
                             kind, ts_url, has_font, has_mermaid)
            hp = html_dir / f"{f.stem}.html"
            hp.write_text(doc, encoding="utf-8")
            page.goto(hp.as_uri())
            page.wait_for_function("window.__done === true", timeout=60_000)
            page.evaluate("document.fonts.ready")
            pdf = f.with_suffix(".pdf")
            page.pdf(path=str(pdf), format="A4", print_background=True,
                     margin={"top": "16mm", "bottom": "16mm", "left": "15mm", "right": "15mm"},
                     display_header_footer=True, header_template="<span></span>", footer_template=FOOTER)
            log(f"   📄 {pdf.name}")
            made.append(pdf)
        browser.close()
    return made


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    out = Path(sys.argv[1]).expanduser().resolve()
    try:
        render(out, sys.argv[2:] or None)
    except RuntimeError as e:
        print(f"❌ PDF 생성 실패\n{e}", file=sys.stderr)
        return 8
    log("✅ PDF 생성 완료")
    return 0


if __name__ == "__main__":
    sys.exit(main())
