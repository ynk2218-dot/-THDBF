"""전처리 진입점.

사용법:
    python scripts/preprocess.py <유튜브 URL | 영상·음성·자막 파일 경로> [--lang ko|en] [--level 기본|심화]

하는 일:
    1) 입력 판별 (URL / 로컬 파일)
    2) 자막 확보: 수동 자막 > 자동 자막 > 음성 인식(faster-whisper)
    3) transcript_raw.md(타임스탬프 유지) / transcript_clean.md(읽기용) 생성
    4) 40분 이상이면 구간(chunks/part_XX.md)으로 분할
    5) meta.json 기록 → 마지막 줄에 OUTPUT_DIR=<폴더> 출력
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from clean import group_blocks, guess_language, render_clean, render_raw, split_chunks  # noqa: E402
from common import ROOT, StudyError, fmt_ts, load_config, log, safe_filename  # noqa: E402
import fetch  # noqa: E402

_created: Path | None = None   # 실패 시 반쯤 만들어진 폴더를 지우기 위해 기억


def is_url(s: str) -> bool:
    return bool(re.match(r"^https?://", s.strip(), re.IGNORECASE))


def make_output_dir(cfg: dict, title: str) -> Path:
    base = ROOT / cfg.get("output_dir", "output")
    name = f"{dt.date.today().isoformat()}_{safe_filename(title)}"
    out = base / name
    n = 2
    while out.exists():
        out = base / f"{name}_{n}"
        n += 1
    (out / "_source").mkdir(parents=True)
    global _created
    _created = out
    return out


def youtube_ts_url(info: dict) -> str | None:
    """타임스탬프를 클릭하면 그 지점으로 가는 링크 틀 (유튜브만)."""
    vid = info.get("id")
    if vid and "youtube" in (info.get("extractor") or "").lower():
        return f"https://youtu.be/{vid}?t={{sec}}"
    return None


def run(args: argparse.Namespace) -> Path:
    cfg = load_config(args.level)
    lang = args.lang or (None if cfg.get("lecture_language", "auto") == "auto" else cfg["lecture_language"])
    src = args.input.strip().strip('"').strip("'")
    meta: dict = {"input": src, "level": cfg["level"], "output_language": cfg.get("output_language", "ko")}

    # ── 1. 입력 판별 ──
    if is_url(src):
        log("① 영상 정보 확인 중…")
        info = fetch.fetch_info(src, cfg)
        title = info.get("title") or "강의"
        duration = float(info.get("duration") or 0)
        out = make_output_dir(cfg, title)
        work = out / "_source"
        meta.update(title=title, url=info.get("webpage_url") or src, channel=info.get("uploader"),
                    duration_sec=duration, ts_url=youtube_ts_url(info))
        log(f"   제목: {title} ({fmt_ts(duration)})")

        log("② 자막 찾는 중… (수동 자막 > 자동 자막)")
        segs, detected = None, lang or info.get("language")
        picked = fetch.pick_subtitle(info, lang)
        if picked:
            kind, key = picked
            log(f"   {'수동' if kind == 'manual' else '자동'} 자막 발견: {key}")
            sub = fetch.download_subtitle(src, cfg, kind, key, work)
            if sub:
                segs = fetch.parse_subtitle(sub)
                meta["transcript_source"] = f"{'manual' if kind == 'manual' else 'auto'}_subtitle:{key}"
                detected = key.split("-")[0]
        if not segs:
            log("   쓸 수 있는 자막이 없습니다 → 오디오를 받아 음성 인식합니다.")
            wav = fetch.download_audio(src, cfg, work)
            from transcribe import transcribe
            segs, detected = transcribe(wav, cfg, lang, duration)
            meta["transcript_source"] = f"whisper:{(cfg.get('whisper') or {}).get('model', 'small')}"
            wav.unlink(missing_ok=True)
    else:
        path = Path(src).expanduser()
        if not path.exists():
            raise StudyError("INPUT_NOT_FOUND", f"파일을 찾을 수 없습니다: {path}",
                             fix="경로에 오타가 없는지, 파일 이름에 따옴표가 필요한지 확인해 주세요. "
                                 "(경로에 공백이 있으면 \"따옴표\"로 감싸 주세요)")
        ext = path.suffix.lower()
        title = path.stem
        out = make_output_dir(cfg, title)
        work = out / "_source"
        meta.update(title=title, url=None, ts_url=None)
        if ext in fetch.SUB_EXTS:
            log("① 자막 파일을 직접 읽습니다.")
            segs = fetch.parse_subtitle(path)
            detected = lang
            meta["transcript_source"] = f"local_subtitle:{path.name}"
            meta["duration_sec"] = segs[-1].end if segs else 0
        else:
            # 같은 이름의 자막 파일이 옆에 있으면 그걸 우선 사용
            side = next((path.with_suffix(e) for e in (".srt", ".vtt") if path.with_suffix(e).exists()), None)
            duration = fetch.probe_duration(path)
            meta["duration_sec"] = duration
            if side:
                log(f"① 같은 이름의 자막 파일을 발견해 사용합니다: {side.name}")
                segs = fetch.parse_subtitle(side)
                detected = lang
                meta["transcript_source"] = f"local_subtitle:{side.name}"
            else:
                log(f"① ffmpeg 로 오디오 추출 중… ({fmt_ts(duration)})")
                wav = fetch.extract_audio(path, work / "audio.wav")
                log("② 음성 인식 중… (영상 길이의 약 0.3~1배 시간이 걸립니다)")
                from transcribe import transcribe
                segs, detected = transcribe(wav, cfg, lang, duration)
                meta["transcript_source"] = f"whisper:{(cfg.get('whisper') or {}).get('model', 'small')}"
                wav.unlink(missing_ok=True)

    if not segs:
        raise StudyError("NO_TRANSCRIPT", "자막과 음성 인식 모두에서 텍스트를 얻지 못했습니다.")

    # ── 2. 정제 ──
    log("③ 전사본 정리 중…")
    duration = meta.get("duration_sec") or segs[-1].end
    meta["duration_sec"] = duration
    meta["lecture_language"] = detected or guess_language(segs)
    hours = duration >= 3600
    blocks = group_blocks(segs)
    work = out / "_source"
    (work / "transcript_raw.md").write_text(render_raw(blocks, meta["title"], hours), encoding="utf-8")
    (work / "transcript_clean.md").write_text(render_clean(blocks, meta["title"], hours), encoding="utf-8")

    # ── 3. 긴 강의 분할 ──
    ll = cfg.get("long_lecture") or {}
    meta["chunks"] = []
    if duration >= float(ll.get("threshold_min", 40)) * 60:
        cdir = work / "chunks"
        cdir.mkdir(exist_ok=True)
        for i, ch in enumerate(split_chunks(blocks, float(ll.get("chunk_min", 15)) * 60), 1):
            rng = f"{fmt_ts(ch[0].start, hours)}–{fmt_ts(ch[-1].end, hours)}"
            name = f"part_{i:02d}.md"
            body = render_raw(ch, f"{meta['title']} · 구간 {i} ({rng})", hours)
            (cdir / name).write_text(body, encoding="utf-8")
            meta["chunks"].append({"file": f"_source/chunks/{name}", "range": rng})
        log(f"   {duration / 60:.0f}분짜리 긴 강의 → {len(meta['chunks'])}개 구간으로 나눴습니다.")

    meta["created"] = dt.datetime.now().isoformat(timespec="seconds")
    meta["config"] = {"level": cfg["level"], "materials": cfg.get("materials")}
    (work / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    log(f"✅ 전처리 완료 — 출처: {meta['transcript_source']}, 언어: {meta['lecture_language']}, "
        f"길이: {fmt_ts(duration)}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="강의 영상 전처리")
    ap.add_argument("input", help="유튜브 URL 또는 영상/음성/자막 파일 경로")
    ap.add_argument("--lang", choices=["ko", "en"], help="강의 언어 (생략하면 자동 감지)")
    ap.add_argument("--level", choices=["기본", "심화"], help="자료 난이도")
    args = ap.parse_args()
    try:
        out = run(args)
    except StudyError as e:
        if _created and not (_created / "_source" / "meta.json").exists():
            shutil.rmtree(_created, ignore_errors=True)
        print(e.report(), file=sys.stderr)
        print(f"STUDY_ERROR={e.code}")
        return e.exit_code
    except KeyboardInterrupt:
        return 130
    print(f"OUTPUT_DIR={out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
