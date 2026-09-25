"""공통 도구: 설정 읽기, 오류 형식, 시간 표기."""
from __future__ import annotations

import copy
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent

# Windows 에서 출력이 파이프로 넘어가면 기본 인코딩이 cp949 라 ✅ 같은 기호에서 멈춘다.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


# ── 오류 ──────────────────────────────────────────────
# 조용히 넘어가지 않기 위해, 실패는 모두 StudyError 로 모아
# "무엇이 / 왜 / 어떻게 하면 되는지"를 한 번에 보여준다.
EXIT_CODES = {
    "INPUT_NOT_FOUND": 2,
    "LOGIN_OR_DRM": 3,
    "NO_TRANSCRIPT": 4,
    "MISSING_TOOL": 5,
    "MODEL_DOWNLOAD": 6,
    "NETWORK": 7,
    "UNKNOWN": 9,
}

MANUAL_FILE_GUIDE = (
    "영상 파일을 직접 받아 경로로 넣어 주세요.\n"
    '  예) /study "C:\\Users\\나\\Downloads\\강의.mp4"\n'
    '      /study "/Users/나/Downloads/강의.mp4"'
)


class StudyError(Exception):
    def __init__(self, code: str, reason: str, fix: str = MANUAL_FILE_GUIDE, detail: str = ""):
        super().__init__(reason)
        self.code = code
        self.reason = reason
        self.fix = fix
        self.detail = detail

    def report(self) -> str:
        lines = [
            f"❌ 전처리 실패 [{self.code}]",
            f"원인: {self.reason}",
            f"해결: {self.fix}",
        ]
        if self.detail:
            lines.append(f"(기술 정보: {self.detail.strip()[:400]})")
        return "\n".join(lines)

    @property
    def exit_code(self) -> int:
        return EXIT_CODES.get(self.code, 9)


# ── 설정 ──────────────────────────────────────────────
def _deep_merge(base: dict, extra: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(level: str | None = None) -> dict:
    path = ROOT / "config.yaml"
    cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    level = level or cfg.get("level", "기본")
    cfg["level"] = level
    override = (cfg.get("level_overrides") or {}).get(level)
    if override:
        cfg = _deep_merge(cfg, override)
    return cfg


# ── 시간 ──────────────────────────────────────────────
def fmt_ts(seconds: float, force_hours: bool = False) -> str:
    s = int(seconds)
    h, m, sec = s // 3600, (s % 3600) // 60, s % 60
    if h or force_hours:
        return f"{h:02d}:{m:02d}:{sec:02d}"
    return f"{m:02d}:{sec:02d}"


def safe_filename(name: str, limit: int = 60) -> str:
    name = re.sub(r'[\\/:*?"<>|\n\r\t]+', " ", name)
    name = re.sub(r"\s+", "_", name.strip())
    return name[:limit].rstrip("._") or "강의"


@dataclass
class Segment:
    start: float
    end: float
    text: str


def log(msg: str) -> None:
    print(msg, flush=True)


def warn(msg: str) -> None:
    print(f"⚠️  {msg}", file=sys.stderr, flush=True)
