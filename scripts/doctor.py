"""설치 점검: python scripts/doctor.py

각 항목을 ✅ / ❌ 로 보여 주고, ❌ 이면 무엇을 실행하면 되는지 알려 준다.
"""
from __future__ import annotations

import importlib
import platform
import shutil
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402,F401  (출력 인코딩을 UTF-8 로 맞춤)

IS_WIN = platform.system() == "Windows"
IS_MAC = platform.system() == "Darwin"
PIP = "python -m pip install -r requirements.txt"
problems = 0


def ok(msg: str) -> None:
    print(f"  ✅ {msg}")


def bad(msg: str, fix: str) -> None:
    global problems
    problems += 1
    print(f"  ❌ {msg}\n     → 해결: {fix}")


def check_python() -> None:
    v = sys.version_info
    if v >= (3, 10):
        ok(f"Python {v.major}.{v.minor}")
    else:
        bad(f"Python {v.major}.{v.minor} (3.10 이상 필요)", "python.org 에서 최신 Python 설치")


def check_ffmpeg() -> None:
    if shutil.which("ffmpeg"):
        ok("ffmpeg")
    else:
        fix = "winget install ffmpeg  (설치 후 터미널을 껐다 켜기)" if IS_WIN else (
            "brew install ffmpeg" if IS_MAC else "sudo apt install ffmpeg")
        bad("ffmpeg 없음", fix)


def check_pkg(mod: str, name: str) -> None:
    try:
        importlib.import_module(mod)
        ok(name)
    except ImportError:
        bad(f"{name} 없음", PIP)


def check_pdf() -> None:
    try:
        from playwright.sync_api import sync_playwright
        from render_pdf import _launch
        from common import load_config
        with sync_playwright() as p:
            b = _launch(p, load_config())
            ok(f"PDF용 브라우저 (Chromium {b.version})")
            b.close()
    except ImportError:
        bad("playwright 없음", PIP)
    except Exception as e:
        bad("PDF용 브라우저를 열 수 없음", f"python -m playwright install chromium\n       ({str(e).splitlines()[0][:150]})")


def check_net(url: str, label: str, why: str) -> None:
    try:
        urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=10)
        ok(f"인터넷: {label}")
    except urllib.error.HTTPError:
        ok(f"인터넷: {label}")  # 응답이 왔다면 연결은 된 것
    except Exception:
        bad(f"인터넷: {label} 에 연결 안 됨", why)


def main() -> int:
    print("\n[1] 기본 도구")
    check_python()
    check_ffmpeg()
    print("\n[2] Python 패키지")
    check_pkg("yt_dlp", "yt-dlp (유튜브)")
    check_pkg("faster_whisper", "faster-whisper (음성 인식)")
    check_pkg("yaml", "PyYAML")
    check_pkg("markdown", "Markdown")
    print("\n[3] PDF")
    check_pdf()
    print("\n[4] 인터넷 연결")
    check_net("https://www.youtube.com", "YouTube", "인터넷 연결 확인 (회사·학교망이면 차단됐을 수 있음)")
    check_net("https://huggingface.co", "HuggingFace (음성 인식 모델)", "첫 음성 인식 때만 필요. 연결 확인")
    print()
    if problems:
        print(f"⚠️  고쳐야 할 항목 {problems}개. 위의 '해결' 명령을 실행한 뒤 다시 점검하세요.")
        return 1
    print("🎉 모두 준비됐습니다. Claude Code 에서  /study <유튜브 주소>  를 실행해 보세요.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
