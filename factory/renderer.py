"""
오당역 — Episode Renderer (120s · 5 quizzes)
- 정적 이미지 배경 루프
- ASS 자막 (5문제 전체 오버레이)
- TTS 120s 에피소드 오디오
- BGM 루프 + -20dB 믹싱 (있을 때)
- 문제 간 전환: 매 24s 경계에서 짧은 플래시
- 카운트다운 구간 (5~8s 내, 각 문제별): 매 초 밝기 펄스
- 정답 공개 시작 시점: 화면 플래시
"""

import random
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
    SEG_CTA,
    QUIZ_DURATION,
    CTA_START,
    TOTAL_DURATION,
    NUM_QUIZZES,
    QUIZ_TRANSITION_FADE_IN,
    QUIZ_TRANSITION_HOLD,
    QUIZ_TRANSITION_FADE_OUT,
    QUIZ_TRANSITION_PEAK,
    CHANNEL_NAME,
    CHANNEL_HEADER_TEXT,
    CHANNEL_HEADER_FONTSIZE,
    CHANNEL_HEADER_Y,
    FONT_BOLD,
)


def _fade_flash_filter(center_t: float, peak: float = None) -> str:
    """
    center_t 를 기준으로 부드러운 화이트 플래시 (페이드인→유지→페이드아웃).
    총 duration = FADE_IN + HOLD + FADE_OUT (기본 1.0s).
    flash 바깥에서는 brightness=0 이라 원본과 동일.
    """
    if peak is None:
        peak = QUIZ_TRANSITION_PEAK
    fi  = QUIZ_TRANSITION_FADE_IN
    hd  = QUIZ_TRANSITION_HOLD
    fo  = QUIZ_TRANSITION_FADE_OUT

    t_start   = center_t - fi - hd / 2     # fade-in 시작
    t_hold_in = center_t - hd / 2          # peak 진입 (hold 시작)
    t_hold_out= center_t + hd / 2          # peak 종료 (hold 끝)
    t_end     = center_t + fo + hd / 2     # fade-out 끝

    # brightness 값:
    #   t_start ~ t_hold_in  : 0 → peak 선형 증가
    #   t_hold_in ~ t_hold_out : peak 유지
    #   t_hold_out ~ t_end   : peak → 0 선형 감소
    #   외부                    : 0
    expr = (
        f"if(between(t\\,{t_start:.3f}\\,{t_hold_in:.3f})\\,"
        f"((t-{t_start:.3f})/{fi:.3f})*{peak:.3f}\\,"
        f"if(between(t\\,{t_hold_in:.3f}\\,{t_hold_out:.3f})\\,"
        f"{peak:.3f}\\,"
        f"if(between(t\\,{t_hold_out:.3f}\\,{t_end:.3f})\\,"
        f"(1-(t-{t_hold_out:.3f})/{fo:.3f})*{peak:.3f}\\,"
        f"0)))"
    )
    return f"eq=brightness='{expr}'"


def _has_ass_filter() -> bool:
    try:
        r = subprocess.run(["ffmpeg", "-filters"], capture_output=True, text=True)
        return " ass " in r.stdout or " subtitles " in r.stdout
    except Exception:
        return False


def _get_bgm() -> Path | None:
    direct = ASSETS_DIR / "bgm_quiz.mp3"
    if direct.exists() and direct.stat().st_size > 10_000:
        return direct
    music_dir = ASSETS_DIR / "music"
    for ext in ("*.mp3", "*.m4a", "*.wav"):
        hits = list(music_dir.glob(ext))
        if hits:
            return random.choice(hits)
    return None


def _font_path() -> str:
    for p in (
        FONT_BOLD,
        "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    ):
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

    font_file   = _font_path()
    fontopt     = f":fontfile={font_file}" if font_file else ""
    bgm_path    = _get_bgm()
    is_image_bg = bg_path.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")

    # ── Subtitle filter ────────────────────────────────────────────────────
    if _has_ass_filter():
        subs_str = str(subs_path).replace("\\", "/").replace(":", "\\:")
        subs_filter = f"ass='{subs_str}',"
    else:
        subs_filter = ""
        print("  [렌더] libass 미존재 — 자막 미적용 경고")

    # ── 시각 이펙트 체인 ────────────────────────────────────────────────────
    fx_parts: list[str] = []

    for qi in range(NUM_QUIZZES):
        base = qi * QUIZ_DURATION

        # 문제 간 부드러운 화이트 플래시 (첫 문제 제외) — 총 1.0s fade
        if qi > 0:
            fx_parts.append(_fade_flash_filter(base))

        # 카운트다운 3초 동안 매 초 펄스 (3, 2, 1)
        for i in range(3):
            st = base + SEG_QUESTION + i
            en = st + 0.12
            fx_parts.append(
                f"eq=brightness=0.18:enable='between(t,{st:.2f},{en:.2f})'"
            )

        # 정답 공개 플래시
        flash_st = base + SEG_QUESTION + SEG_COUNTDOWN
        flash_en = flash_st + 0.25
        fx_parts.append(
            f"eq=brightness=0.40:enable='between(t,{flash_st:.2f},{flash_en:.2f})'"
        )

    # 퀴즈 → CTA 전환도 같은 부드러운 페이드 플래시 적용
    fx_parts.append(_fade_flash_filter(CTA_START, peak=0.55))
    # CTA 구간 전체에 살짝 어두운 tint 유지 — 문자 가독성
    fx_parts.append(
        f"eq=brightness=-0.12:enable='between(t,{CTA_START:.2f},{TOTAL_DURATION:.2f})'"
    )

    fx_chain = ",".join(fx_parts) + "," if fx_parts else ""

    # ── 채널 헤더 (상단 중앙, 전체 132초 고정, 노란색 + 검은 외곽선) ────────
    channel_header = (
        f"drawtext=text='{CHANNEL_HEADER_TEXT}'"
        f"{fontopt}"
        f":fontsize={CHANNEL_HEADER_FONTSIZE}:fontcolor=yellow"
        f":bordercolor=black:borderw=6"
        f":x=(w-text_w)/2:y={CHANNEL_HEADER_Y},"
    )

    # ── CTA 배지 3개 (각 4초, 중앙 대형) ──────────────────────────────────
    # 색 이모지(👍🔔)는 NanumGothicBold 에 없어 tofu(□×) 로 렌더 → 기본 폰트에
    # 존재하는 기하 심볼(♥ ✔ ★)로 교체해 정상 표시되도록.
    _badge_dur = SEG_CTA / 3.0                     # 4.0s
    badges: list[tuple[float, float, str]] = [
        (CTA_START + 0 * _badge_dur, CTA_START + 1 * _badge_dur, "♥ 좋아요"),
        (CTA_START + 1 * _badge_dur, CTA_START + 2 * _badge_dur, "✔ 구독"),
        (CTA_START + 2 * _badge_dur, CTA_START + 3 * _badge_dur, "★ 알림설정"),
    ]
    cta_badges = ""
    for st, en, text in badges:
        cta_badges += (
            f"drawtext=text='{text}'"
            f"{fontopt}"
            f":fontsize=160:fontcolor=yellow"
            f":bordercolor=black:borderw=10"
            f":x=(w-text_w)/2:y=(h-text_h)/2"
            f":enable='between(t,{st:.2f},{en:.2f})',"
        )

    video_chain = (
        f"[0:v]"
        f"trim=duration={TOTAL_DURATION:.3f},setpts=PTS-STARTPTS,"
        f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={VIDEO_WIDTH}:{VIDEO_HEIGHT},setsar=1,"
        f"fps={VIDEO_FPS},format=yuv420p,"
        f"{fx_chain}"
        f"{subs_filter}"
        f"{channel_header}"
        f"{cta_badges}"
        f"fade=t=in:st=0:d=0.4,"
        f"fade=t=out:st={TOTAL_DURATION - 0.6:.3f}:d=0.6"
        f"[vfinal]"
    )

    tts_chain = f"[1:a]volume={TTS_VOLUME}[tts]"

    if bgm_path:
        bgm_chain = (
            f"[2:a]volume={BGM_VOLUME},"
            f"aloop=loop=-1:size=2147483647,"
            f"atrim=duration={TOTAL_DURATION:.3f},asetpts=PTS-STARTPTS,"
            f"afade=t=in:st=0:d=1.0,"
            f"afade=t=out:st={TOTAL_DURATION - 1.5:.3f}:d=1.5[bgm]"
        )
        mix = "[tts][bgm]amix=inputs=2:duration=first:normalize=0[afinal]"
        filter_complex = f"{video_chain};{tts_chain};{bgm_chain};{mix}"
        audio_map = "[afinal]"
    else:
        filter_complex = f"{video_chain};{tts_chain}"
        audio_map = "[tts]"

    cmd = ["ffmpeg", "-y"]
    if is_image_bg:
        cmd += ["-loop", "1", "-framerate", str(VIDEO_FPS), "-i", str(bg_path)]
    else:
        cmd += ["-stream_loop", "-1", "-i", str(bg_path)]
    cmd += ["-i", str(audio_path)]
    if bgm_path:
        cmd += ["-i", str(bgm_path)]

    cmd += [
        "-filter_complex", filter_complex,
        "-map", "[vfinal]",
        "-map", audio_map,
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
    bgm_msg = f" + BGM({bgm_path.name})" if bgm_path else " (BGM 없음)"
    print(f"  [렌더] FFmpeg — {TOTAL_DURATION:.0f}s · {NUM_QUIZZES}문제{bgm_msg}")

    r = subprocess.run(cmd, capture_output=True, timeout=900)
    if r.returncode != 0:
        err = r.stderr.decode("utf-8", errors="replace")[-1500:]
        raise RuntimeError(f"FFmpeg 실패:\n{err}")

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"  [렌더] 완료: {output_path.name} ({size_mb:.1f} MB)")
    return output_path
