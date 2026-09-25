"""faster-whisper 음성 인식 (한국어·영어)."""
from __future__ import annotations

import time
from pathlib import Path

from common import Segment, StudyError, fmt_ts, log


def _pick_device(cfg: dict) -> tuple[str, str]:
    device = cfg.get("device", "auto")
    compute = cfg.get("compute_type", "auto")
    if device == "auto":
        try:
            import ctranslate2
            device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
        except Exception:
            device = "cpu"
    if compute == "auto":
        compute = "float16" if device == "cuda" else "int8"
    return device, compute


def transcribe(audio: Path, cfg: dict, lang: str | None, duration: float) -> tuple[list[Segment], str]:
    """(세그먼트 목록, 감지된 언어) 반환."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise StudyError("MISSING_TOOL", "faster-whisper 가 설치되어 있지 않습니다.",
                         fix="README.md 의 'Python 패키지 설치' 단계를 다시 실행하세요.") from None

    wcfg = cfg.get("whisper") or {}
    model_name = wcfg.get("model", "small")
    device, compute = _pick_device(wcfg)
    log(f"   음성 인식 모델 준비: {model_name} ({device}/{compute}) — 첫 실행이면 모델을 내려받습니다.")
    try:
        model = WhisperModel(model_name, device=device, compute_type=compute)
    except Exception as e:  # 모델 다운로드 실패가 대부분
        raise StudyError(
            "MODEL_DOWNLOAD",
            f"음성 인식 모델({model_name})을 불러오지 못했습니다. 첫 실행 때는 인터넷으로 모델을 받아야 합니다.",
            fix="인터넷 연결을 확인하고 다시 실행하세요. (모델 저장소: huggingface.co)",
            detail=repr(e),
        ) from None

    segments, info = model.transcribe(
        str(audio),
        language=lang,
        vad_filter=True,               # 무음 구간 건너뛰기 → 환각(없는 말 생성) 감소
        beam_size=5,
        condition_on_previous_text=False,  # 같은 문장이 반복 생성되는 현상 방지
    )
    log(f"   감지된 언어: {info.language} (확률 {info.language_probability:.2f})")
    out: list[Segment] = []
    t0, last_report = time.time(), 0.0
    for s in segments:
        text = s.text.strip()
        if text:
            out.append(Segment(s.start, s.end, text))
        if duration and s.end - last_report > 60:
            last_report = s.end
            log(f"   … {fmt_ts(s.end)} / {fmt_ts(duration)} ({time.time() - t0:.0f}초 경과)")
    if not out:
        raise StudyError("NO_TRANSCRIPT", "음성 인식 결과가 비어 있습니다(말소리가 거의 없는 영상일 수 있음).")
    return out, info.language
