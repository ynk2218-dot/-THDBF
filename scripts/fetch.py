"""입력 확보: 유튜브 등 URL(yt-dlp) / 로컬 파일(ffmpeg) / 자막 파일 파싱."""
from __future__ import annotations

import html
import re
import shutil
import subprocess
from pathlib import Path

from common import Segment, StudyError, log, warn

SUB_EXTS = {".vtt", ".srt"}


# ── 오류 분류 ────────────────────────────────────────
# yt-dlp 의 영문 오류 메시지를 "사람이 할 수 있는 조치"로 바꿔 준다.
_LOGIN_PATTERNS = [
    "private video", "members-only", "join this channel", "requires payment",
    "log in", "login", "sign in to", "registered users", "premium", "purchase",
    "age-restricted", "confirm your age", "cookies",
]


def classify_ytdlp_error(msg: str) -> StudyError:
    low = msg.lower()
    if "drm" in low:
        return StudyError("LOGIN_OR_DRM", "영상에 DRM(복제 방지)이 걸려 있어 받을 수 없습니다.", detail=msg)
    if "unsupported url" in low:
        return StudyError(
            "LOGIN_OR_DRM",
            "지원하지 않는 사이트입니다. 유료 인강 사이트는 대부분 로그인·DRM 때문에 자동으로 받을 수 없습니다.",
            detail=msg,
        )
    if "sign in to confirm" in low and "bot" in low:
        return StudyError(
            "LOGIN_OR_DRM",
            "YouTube가 '로봇이 아닌지 확인'을 요구해 다운로드가 막혔습니다.",
            fix=(
                "config.yaml 의 ytdlp.cookies_from_browser 에 평소 쓰는 브라우저 이름(chrome, edge, safari, firefox)을 "
                "적고 다시 실행하거나, 영상 파일을 직접 받아 경로로 넣어 주세요."
            ),
            detail=msg,
        )
    if any(p in low for p in _LOGIN_PATTERNS):
        return StudyError("LOGIN_OR_DRM", "로그인·구매·연령 인증이 필요한 영상이라 자동으로 받을 수 없습니다.", detail=msg)
    if "video unavailable" in low or "not available" in low or "404" in low:
        return StudyError(
            "INPUT_NOT_FOUND", "영상을 찾을 수 없습니다(삭제·비공개·지역 제한 또는 주소 오타).",
            fix="주소를 다시 확인하거나, 영상 파일을 직접 받아 경로로 넣어 주세요.", detail=msg,
        )
    if any(p in low for p in ["timed out", "getaddrinfo", "network", "connection", "403", "proxy", "ssl"]):
        return StudyError(
            "NETWORK", "인터넷 연결 또는 네트워크 차단 때문에 영상 정보를 가져오지 못했습니다.",
            fix="인터넷 연결을 확인하고 다시 실행하세요. 계속 실패하면 영상 파일을 직접 받아 경로로 넣어 주세요.",
            detail=msg,
        )
    return StudyError("UNKNOWN", "영상 정보를 가져오는 중 알 수 없는 오류가 났습니다.", detail=msg)


# ── 자막 파싱 ────────────────────────────────────────
_TS = r"(\d{1,2}:)?\d{1,2}:\d{2}[.,]\d{1,3}"
_CUE_RE = re.compile(rf"^\s*({_TS})\s*-->\s*({_TS})")


def _to_sec(ts: str) -> float:
    ts = ts.replace(",", ".")
    parts = ts.split(":")
    parts = [0.0] * (3 - len(parts)) + [float(p) for p in parts]
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def _clean_cue_line(line: str) -> str:
    line = re.sub(r"<[^>]+>", "", line)          # <c>, <00:00:01.000> 등 태그
    line = re.sub(r"\{\\[^}]*\}", "", line)       # ASS 스타일 태그
    line = html.unescape(line).replace("​", "")
    return re.sub(r"\s+", " ", line).strip()


def parse_subtitle(path: Path) -> list[Segment]:
    """VTT/SRT 를 읽어 세그먼트로. 유튜브 자동자막의 '굴러가는 중복 줄'도 제거."""
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    lines = text.splitlines()
    cues: list[tuple[float, float, list[str]]] = []
    i = 0
    while i < len(lines):
        m = _CUE_RE.match(lines[i])
        if not m:
            i += 1
            continue
        start, end = _to_sec(m.group(1)), _to_sec(m.group(3))
        i += 1
        body = []
        while i < len(lines) and lines[i].strip() and not _CUE_RE.match(lines[i]):
            body.append(lines[i])
            i += 1
        cues.append((start, end, body))

    segs: list[Segment] = []
    last_line = ""
    for start, end, body in cues:
        if end - start < 0.05:          # 자동자막의 10ms 짜리 '잔상' 큐
            continue
        for raw in body:
            line = _clean_cue_line(raw)
            if not line or line == last_line:
                continue
            # 이전 줄이 이번 줄의 앞부분이면(점점 늘어나는 자막) 새 부분만 남김
            if last_line and line.startswith(last_line):
                line = line[len(last_line):].strip()
                if not line:
                    continue
            segs.append(Segment(start, end, line))
            last_line = _clean_cue_line(raw)
    return segs


# ── 오디오 ───────────────────────────────────────────
def require_ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise StudyError(
            "MISSING_TOOL", "ffmpeg 가 설치되어 있지 않습니다.",
            fix="README.md 의 'ffmpeg 설치' 단계를 따라 설치한 뒤 다시 실행하세요. "
                "(Mac: brew install ffmpeg / Windows: winget install ffmpeg)",
        )
    return exe


def extract_audio(src: Path, dst: Path) -> Path:
    """ffmpeg 로 16kHz 모노 wav 추출 (음성 인식에 최적, 용량도 작음)."""
    ffmpeg = require_ffmpeg()
    cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(src),
           "-vn", "-ac", "1", "-ar", "16000", "-f", "wav", str(dst)]
    r = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    if r.returncode != 0 or not dst.exists() or dst.stat().st_size < 1000:
        err = (r.stderr or "").lower()
        if "does not contain any stream" in err or "matches no streams" in err:
            raise StudyError("NO_TRANSCRIPT", "이 파일에는 소리(오디오 트랙)가 없습니다.",
                             fix="소리가 들어 있는 원본 영상 파일인지 확인해 주세요.", detail=r.stderr)
        if "drm" in err or "encrypt" in err or "invalid data" in err:
            raise StudyError(
                "LOGIN_OR_DRM",
                "파일이 암호화(DRM)되어 있거나 손상되어 소리를 꺼낼 수 없습니다. "
                "인강 앱 전용 다운로드 파일은 보통 이런 경우입니다.",
                fix="일반 동영상 플레이어에서 재생되는 파일(mp4, mkv, mp3 등)로 다시 받아 경로로 넣어 주세요.",
                detail=r.stderr,
            )
        raise StudyError("NO_TRANSCRIPT", "오디오 추출에 실패했습니다.", detail=r.stderr)
    return dst


def probe_duration(path: Path) -> float:
    exe = shutil.which("ffprobe")
    if not exe:
        return 0.0
    r = subprocess.run([exe, "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", str(path)], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


# ── URL (yt-dlp) ─────────────────────────────────────
class _SilentLogger:
    """yt-dlp 가 직접 찍는 영문 ERROR 줄을 숨긴다 (오류는 우리가 한국어로 정리해 보여줌)."""
    def debug(self, msg): pass
    def info(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass


def _ydl_base_opts(cfg: dict) -> dict:
    opts = {"quiet": True, "no_warnings": True, "noplaylist": True, "noprogress": True,
            "logger": _SilentLogger()}
    browser = ((cfg.get("ytdlp") or {}).get("cookies_from_browser") or "").strip()
    if browser:
        opts["cookiesfrombrowser"] = (browser,)
    return opts


def fetch_info(url: str, cfg: dict) -> dict:
    from yt_dlp import YoutubeDL
    from yt_dlp.utils import DownloadError

    try:
        with YoutubeDL({**_ydl_base_opts(cfg), "skip_download": True}) as ydl:
            info = ydl.extract_info(url, download=False)
    except DownloadError as e:
        raise classify_ytdlp_error(str(e)) from None
    if info.get("_type") == "playlist":
        entries = [e for e in info.get("entries") or [] if e]
        if not entries:
            raise StudyError("INPUT_NOT_FOUND", "재생목록에 영상이 없습니다.", fix="영상 하나의 주소를 넣어 주세요.")
        warn("재생목록 주소입니다. 첫 번째 영상만 처리합니다.")
        info = entries[0]
    return info


def _norm(code: str | None) -> str:
    return (code or "").split("-")[0].lower()


def pick_subtitle(info: dict, lang: str | None) -> tuple[str, str] | None:
    """(종류, 언어키) 반환. 수동 자막 > 자동 자막(원어 인식본만) 순."""
    manual = {k: v for k, v in (info.get("subtitles") or {}).items() if k != "live_chat"}
    auto = info.get("automatic_captions") or {}
    orig = info.get("language")

    wanted = [x for x in [lang, orig, "ko", "en"] if x]
    for w in wanted:
        for k in manual:
            if k == w or _norm(k) == _norm(w):
                return "manual", k
    if manual and not lang:
        return "manual", next(iter(manual))

    # 자동자막 목록에는 '자동 번역본'이 수십 개 섞여 있다. 번역본은 품질이 낮으므로
    # 강의 원어로 인식한 트랙(xx-orig, 또는 원어 코드)만 쓴다.
    orig_keys = [k for k in auto if k.endswith("-orig")]
    if orig_keys:
        return "auto", orig_keys[0]
    for w in [orig, lang]:
        if w and w in auto:
            return "auto", w
    return None


def download_subtitle(url: str, cfg: dict, kind: str, key: str, workdir: Path) -> Path | None:
    from yt_dlp import YoutubeDL
    from yt_dlp.utils import DownloadError

    opts = {
        **_ydl_base_opts(cfg),
        "skip_download": True,
        "writesubtitles": kind == "manual",
        "writeautomaticsub": kind == "auto",
        "subtitleslangs": [key],
        "subtitlesformat": "vtt/srt/best",
        "outtmpl": str(workdir / "subtitle.%(ext)s"),
    }
    try:
        with YoutubeDL(opts) as ydl:
            ydl.download([url])
    except DownloadError as e:
        warn(f"자막 다운로드 실패 → 음성 인식으로 전환합니다. ({e})")
        return None
    found = sorted(p for p in workdir.glob("subtitle*") if p.suffix in SUB_EXTS)
    return found[0] if found else None


def download_audio(url: str, cfg: dict, workdir: Path) -> Path:
    from yt_dlp import YoutubeDL
    from yt_dlp.utils import DownloadError

    opts = {
        **_ydl_base_opts(cfg),
        "format": "bestaudio/best",
        "outtmpl": str(workdir / "audio_src.%(ext)s"),
    }
    log("   오디오 내려받는 중…")
    try:
        with YoutubeDL(opts) as ydl:
            ydl.download([url])
    except DownloadError as e:
        raise classify_ytdlp_error(str(e)) from None
    srcs = [p for p in workdir.glob("audio_src.*") if p.suffix not in {".part", ".ytdl"}]
    if not srcs:
        raise StudyError("NO_TRANSCRIPT", "자막도 없고 오디오도 내려받지 못했습니다.")
    wav = extract_audio(srcs[0], workdir / "audio.wav")
    srcs[0].unlink(missing_ok=True)   # 원본 오디오는 용량만 차지하므로 삭제
    return wav
