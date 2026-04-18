"""
오당역 — Renderer
60초 쇼츠 영상 합성:
  - 정적 이미지 배경을 루프
  - ASS 자막 (질문/카운트다운/정답/해설 오버레이 포함)
  - TTS 오디오 (60초 4-segment 합성본)
  - 선택: 카운트다운 구간 (5~10s)에 비프 효과, 정답 구간 시작에 딩동 효과, BGM
  - 채널 워터마크
"""

import random
import re
import shutil
import subprocess
from pathlib import Path

from config import (
    VIDEO_WIDTH,
    VIDEO_HEIGHT,
    VIDEO_FPS,
    VIDEO_CODEC,
    VIDEO_PRESET,
    VIDEO_CRF,
    AUDIO_CODEC,
    AUDIO_BITRATE,
    BGM_VOLUME,
    TTS_VOLUME,
    ASSETS_DIR,
    SEG_QUESTION,
    SEG_COUNTDOWN,
    SEG_REVEAL,
    TOTAL_DURATION,
    CHANNEL_NAME,
    FONT_BOLD,
)


def _has_ass_filter() -> bool:
    try:
        r = subprocess.run(["ffmpeg", "-filters"], capture_output=True, text=True)
        return " ass " in r.stdout or " subtitles " in r.stdout
    except Exception:
        return False


def _get_bgm() -> Path | None:
    direct = ASSETS_DIR / "bgm_quiz.mp3"
    if direct.exists():
        return direct
    music_dir = ASSETS_DIR / "music"
    for ext in ("*.mp3", "*.m4a", "*.wav"):
        hits = list(music_dir.glob(ext))
        if hits:
            return random.choice(hits)
    return None


def _font_path() -> str:
    candidates = [
        FONT_BOLD,
        "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    ]
    for p in candidates:
        if p and Path(p).exists():
            return p
    return ""


def render_video(
    audio_path: Path,
    bg_path: Path,
    subs_path: Path,
    output_path: Path,
) -> Path:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg 미설치")

    font_file = _font_path()
    fontfile_opt = f":fontfile={font_file}" if font_file else ""

    bgm = _get_bgm()

    # ── Subtitle filter ────────────────────────────────────────────────────
    if _has_ass_filter():
        subs_str = str(subs_path).replace("\\", "/").replace(":", "\\:")
        subs_filter = f"ass='{subs_str}',"
    else:
        subs_filter = ""
        print("  [렌더] libass 필터 없음 — 자막 미적용 경고")

    # ── 시대 배지 + 채널 워터마크 ──────────────────────────────────────────
    watermark = (
        f"drawtext=text='{CHANNEL_NAME}'"
        f"{fontfile_opt}"
        f":fontsize=38:fontcolor=white@0.85"
        f":x=30:y=30"
        f":box=1:boxcolor=black@0.55:boxborderw=12,"
    )

    # ── 카운트다운 구간 밝기 펄스 (시각 임팩트) ────────────────────────────
    # 5~10s 에서 매 초 밝기 살짝 증가
    pulses = []
    for i in range(5):
        st = SEG_QUESTION + i
        en = st + 0.15
        pulses.append(
            f"eq=brightness=0.15:enable='between(t,{st:.2f},{en:.2f})'"
        )
    pulse_filter = ",".join(pulses) + "," if pulses else ""

    # 정답 공개 시작 (10s) 화면 플래시
    flash_start = SEG_QUESTION + SEG_COUNTDOWN
    flash_end   = flash_start + 0.3
    flash_filter = (
        f"eq=brightness=0.30:enable='between(t,{flash_start:.2f},{flash_end:.2f})',"
    )

    is_image_bg = bg_path.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")

    video_chain = (
        f"[0:v]"
        f"trim=duration={TOTAL_DURATION:.3f},setpts=PTS-STARTPTS,"
        f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={VIDEO_WIDTH}:{VIDEO_HEIGHT},setsar=1,"
        f"fps={VIDEO_FPS},format=yuv420p,"
        f"{pulse_filter}"
        f"{flash_filter}"
        f"{subs_filter}"
        f"{watermark}"
        f"fade=t=in:st=0:d=0.4,"
        f"fade=t=out:st={TOTAL_DURATION - 0.6:.3f}:d=0.6"
        f"[vfinal]"
    )

    tts_chain = (
        f"[1:a]volume={TTS_VOLUME}[tts]"
    )

    if bgm:
        bgm_chain = (
            f"[2:a]volume={BGM_VOLUME},"
            f"aloop=loop=-1:size=2147483647,"
            f"atrim=duration={TOTAL_DURATION:.3f},asetpts=PTS-STARTPTS,"
            f"afade=t=in:st=0:d=1.0,"
            f"afade=t=out:st={TOTAL_DURATION - 1.5:.3f}:d=1.5[bgm]"
        )
        mix = "[tts][bgm]amix=inputs=2:duration=first:normalize=0[afinal]"
        filter_complex = f"{video_chain};{tts_chain};{bgm_chain};{mix}"
    else:
        filter_complex = f"{video_chain};{tts_chain}"

    cmd = ["ffmpeg", "-y"]
    if is_image_bg:
        cmd += ["-loop", "1", "-framerate", str(VIDEO_FPS), "-i", str(bg_path)]
    else:
        cmd += ["-stream_loop", "-1", "-i", str(bg_path)]
    cmd += ["-i", str(audio_path)]
    if bgm:
        cmd += ["-i", str(bgm)]

    cmd += [
        "-filter_complex", filter_complex,
        "-map", "[vfinal]",
        "-map", "[afinal]" if bgm else "[tts]",
        "-c:v", VIDEO_CODEC,
        "-preset", VIDEO_PRESET,
        "-crf", str(VIDEO_CRF),
        "-pix_fmt", "yuv420p",
        "-c:a", AUDIO_CODEC,
        "-b:a", AUDIO_BITRATE,
        "-t", str(TOTAL_DURATION),
        "-movflags", "+faststart",
        str(output_path),
    ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"  [렌더] FFmpeg 실행 ({TOTAL_DURATION:.0f}초)...")
    r = subprocess.run(cmd, capture_output=True, timeout=600)
    if r.returncode != 0:
        err = r.stderr.decode("utf-8", errors="replace")[-1200:]
        raise RuntimeError(f"FFmpeg 실패:\n{err}")

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"  [렌더] 완료: {output_path.name} ({size_mb:.1f} MB)")
    return output_path
