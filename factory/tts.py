"""
오당역 — TTS (episode audio = 5 × 24s = 120s)

각 퀴즈 24초 구성:
  0.0 ~ 5.0   문제 TTS      (OpenAI nova)
  5.0 ~ 8.0   카운트다운     (비프 3개: hi@0.0s · hi@1.0s · low-strong@2.0s)
  8.0 ~ 11.0  정답 TTS      (OpenAI onyx)
  11.0 ~ 24.0 해설 TTS      (OpenAI shimmer, speed=1.05)

최종 출력: 120초 MP3 단일 파일.
"""

import json
import re
import subprocess
from pathlib import Path

from openai import OpenAI

from config import (
    OPENAI_API_KEY,
    TTS_MODEL,
    TTS_VOICE_QUESTION,
    TTS_VOICE_REVEAL,
    TTS_VOICE_EXPLAIN,
    TTS_VOICE_CTA,
    TTS_SPEED_QUESTION,
    TTS_SPEED_EXPLAIN,
    TTS_SPEED_CTA,
    SEG_QUESTION,
    SEG_COUNTDOWN,
    SEG_REVEAL,
    SEG_EXPLANATION,
    SEG_CTA,
    QUIZ_DURATION,
    CTA_START,
    TOTAL_DURATION,
    AUDIO_BITRATE,
)


# ── 숫자 → 한국어 ─────────────────────────────────────────────────────────────
def _num_to_ko(n: int) -> str:
    if n == 0:
        return "영"
    units = ["", "일", "이", "삼", "사", "오", "육", "칠", "팔", "구"]
    small = ["", "십", "백", "천"]
    big   = ["", "만", "억", "조"]

    def _chunk(v: int) -> str:
        if v == 0:
            return ""
        out = ""
        for i in range(3, -1, -1):
            d = (v // (10 ** i)) % 10
            if d == 0:
                continue
            out += (small[i] if d == 1 and i > 0 else units[d] + small[i])
        return out

    result = ""
    for i in range(3, -1, -1):
        chunk = (n // (10000 ** i)) % 10000
        if chunk == 0:
            continue
        result += _chunk(chunk) + big[i]
    return result


def _convert_numbers(text: str) -> str:
    return re.sub(r"\d+", lambda m: _num_to_ko(int(m.group())), text)


def _get_duration(path: Path) -> float:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(path)],
            capture_output=True, text=True, timeout=30,
        )
        return float(json.loads(r.stdout)["format"]["duration"])
    except Exception:
        return 0.0


def _clean(text: str) -> str:
    t = re.sub(r"\*{1,3}(.+?)\*{1,3}", r"\1", text)
    t = re.sub(r"^#{1,6}\s+.*$", "", t, flags=re.MULTILINE)
    t = re.sub(r"\[.*?\]", "", t)
    return t.strip()


# ── 기본 오디오 블록 ──────────────────────────────────────────────────────────
def _openai_tts(text: str, voice: str, speed: float, out_path: Path) -> None:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY 미설정")
    client = OpenAI(api_key=OPENAI_API_KEY)
    resp = client.audio.speech.create(
        model=TTS_MODEL, voice=voice, input=text, speed=speed,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    resp.stream_to_file(str(out_path))


def _pad_or_trim(src: Path, target: float, out: Path) -> None:
    """
    TTS 원본의 앞쪽 무음을 제거해 음성이 t=0부터 즉시 시작하도록 하고,
    이어서 target 초에 맞춰 뒷쪽을 패딩 또는 트림.
    OpenAI TTS 가 서두에 넣는 0.2~0.4s 무음이 자막 싱크 밀림 원인.
    """
    cmd = [
        "ffmpeg", "-y",
        "-i", str(src),
        "-af", (
            "silenceremove=start_periods=1:start_duration=0.05:start_threshold=-45dB,"
            f"apad=whole_dur={target:.3f}"
        ),
        "-t", f"{target:.3f}",
        "-ac", "1",
        "-ar", "44100",
        "-c:a", "libmp3lame", "-b:a", AUDIO_BITRATE,
        str(out),
    ]
    subprocess.run(cmd, capture_output=True, timeout=60, check=True)


def _concat(segments: list[Path], out_path: Path) -> None:
    list_file = out_path.with_suffix(".list.txt")
    list_file.write_text(
        "\n".join(f"file '{p.resolve()}'" for p in segments), encoding="utf-8"
    )
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(list_file),
        "-ac", "1", "-ar", "44100",
        "-c:a", "libmp3lame", "-b:a", AUDIO_BITRATE,
        str(out_path),
    ]
    subprocess.run(cmd, capture_output=True, timeout=120, check=True)
    list_file.unlink(missing_ok=True)


# ── 카운트다운 비프 (3초) ────────────────────────────────────────────────────
def _countdown_beeps(out_path: Path) -> None:
    """
    3초 카운트다운 — t=0.0 삐(900Hz), t=1.0 삐(900Hz), t=2.0 뚜--(500Hz 강조)
    """
    fc = (
        # 3초 무음 베이스
        # beep1: 3초 숫자용 (짧고 맑음)
        "[1:a]adelay=0|0,afade=d=0.015,afade=t=out:st=0.16:d=0.03,volume=0.9[b1];"
        # beep2: 2초 숫자용
        "[2:a]adelay=1000|1000,afade=d=0.015,afade=t=out:st=0.16:d=0.03,volume=0.9[b2];"
        # beep3: 1초 숫자용 (낮은 주파수 + 길이 + 볼륨 ↑ → 마지막 강조)
        "[3:a]adelay=2000|2000,afade=d=0.02,afade=t=out:st=0.50:d=0.08,volume=1.8[b3];"
        "[0:a][b1][b2][b3]amix=inputs=4:duration=first:normalize=0,"
        "atrim=duration=3.0,asetpts=PTS-STARTPTS"
    )
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-t", "3.0", "-i", "anullsrc=r=44100:cl=mono",
        "-f", "lavfi", "-i", "sine=frequency=900:duration=0.20:sample_rate=44100",
        "-f", "lavfi", "-i", "sine=frequency=900:duration=0.20:sample_rate=44100",
        "-f", "lavfi", "-i", "sine=frequency=500:duration=0.60:sample_rate=44100",
        "-filter_complex", fc,
        "-ac", "1", "-ar", "44100",
        "-c:a", "libmp3lame", "-b:a", AUDIO_BITRATE,
        str(out_path),
    ]
    subprocess.run(cmd, capture_output=True, timeout=60, check=True)


# ── 문제 하나의 24s 오디오 ───────────────────────────────────────────────────
def _build_quiz_audio(quiz: dict, idx: int, job_dir: Path) -> Path:
    """한 퀴즈 = Q(5s) + CD(3s) + R(3s) + E(13s) = 24s.

    TTS 는 질문 본문만 읽음 (4지선다 보기는 자막으로만 표시 — 5초 안에 다 읽히게).
    """
    q_text = _clean(quiz["question"])

    if quiz["type"] == "OX":
        # "O" / "X" 알파벳 그대로 읽으면 TTS 가 영어식 ('오우'/'엑스') 로
        # 발음하거나 불일치할 수 있어 한국어 발음으로 명시 변환.
        ans_ko = "오" if quiz["answer"] == "O" else "엑스"
        reveal_text = f"정답은 {ans_ko}!"
    else:
        ans_idx = int(quiz["answer"]) - 1
        opts = quiz.get("options", [])
        ans_val = opts[ans_idx] if 0 <= ans_idx < len(opts) else ""
        reveal_text = f"정답은 {quiz['answer']}번, {ans_val}!"

    explain_text = _clean(quiz["explanation"])

    # 숫자 한글 전처리
    q_text       = _convert_numbers(q_text)
    reveal_text  = _convert_numbers(reveal_text)
    explain_text = _convert_numbers(explain_text)

    prefix = f"q{idx+1:02d}"

    # 1. 문제 (5s)
    q_raw = job_dir / f"{prefix}_question_raw.mp3"
    q_out = job_dir / f"{prefix}_question.mp3"
    _openai_tts(q_text, TTS_VOICE_QUESTION, TTS_SPEED_QUESTION, q_raw)
    _pad_or_trim(q_raw, SEG_QUESTION, q_out)

    # 2. 카운트다운 비프 (3s)
    cd_out = job_dir / f"{prefix}_countdown.mp3"
    _countdown_beeps(cd_out)

    # 3. 정답 (3s)
    r_raw = job_dir / f"{prefix}_reveal_raw.mp3"
    r_out = job_dir / f"{prefix}_reveal.mp3"
    _openai_tts(reveal_text, TTS_VOICE_REVEAL, 1.0, r_raw)
    _pad_or_trim(r_raw, SEG_REVEAL, r_out)

    # 4. 해설 (13s)
    e_raw = job_dir / f"{prefix}_explain_raw.mp3"
    e_out = job_dir / f"{prefix}_explain.mp3"
    _openai_tts(explain_text, TTS_VOICE_EXPLAIN, TTS_SPEED_EXPLAIN, e_raw)
    _pad_or_trim(e_raw, SEG_EXPLANATION, e_out)

    # 합치기 (24s)
    quiz_out = job_dir / f"{prefix}_combined.mp3"
    _concat([q_out, cd_out, r_out, e_out], quiz_out)

    # 임시 raw 정리
    for p in [q_raw, r_raw, e_raw]:
        p.unlink(missing_ok=True)

    return quiz_out


# ── CTA 아웃트로 30s ─────────────────────────────────────────────────────────
def _build_cta_audio(cta_text: str, job_dir: Path) -> Path:
    cta_clean = _convert_numbers(_clean(cta_text))
    c_raw = job_dir / "cta_raw.mp3"
    c_out = job_dir / "cta.mp3"
    _openai_tts(cta_clean, TTS_VOICE_CTA, TTS_SPEED_CTA, c_raw)
    _pad_or_trim(c_raw, SEG_CTA, c_out)
    c_raw.unlink(missing_ok=True)
    return c_out


# ── 공개 API ──────────────────────────────────────────────────────────────────
def generate_episode_tts(
    quizzes: list[dict],
    cta_text: str,
    output_path: Path,
    job_dir: Path,
) -> tuple[Path, list[dict]]:
    """
    n개 퀴즈 + CTA → 150s (= n*24 + 30) MP3 단일 파일.
    반환: (output_path, segment_info_list) — 퀴즈별 + CTA 구간 정보.
    """
    job_dir.mkdir(parents=True, exist_ok=True)
    parts: list[Path] = []
    segments: list[dict] = []

    for i, quiz in enumerate(quizzes):
        print(f"  [TTS] 문제 {i+1}/{len(quizzes)} — [{quiz.get('era','')}/{quiz['type']}] 합성 중...")
        qa = _build_quiz_audio(quiz, i, job_dir)
        parts.append(qa)

        base = i * QUIZ_DURATION
        segments.append({
            "quiz_idx":     i,
            "base":         base,
            "question":     {"start": base,                                        "end": base + SEG_QUESTION},
            "countdown":    {"start": base + SEG_QUESTION,                         "end": base + SEG_QUESTION + SEG_COUNTDOWN},
            "reveal":       {"start": base + SEG_QUESTION + SEG_COUNTDOWN,         "end": base + SEG_QUESTION + SEG_COUNTDOWN + SEG_REVEAL},
            "explanation":  {"start": base + SEG_QUESTION + SEG_COUNTDOWN + SEG_REVEAL, "end": base + QUIZ_DURATION},
        })

    print(f"  [TTS] CTA 아웃트로 ({len(cta_text)}자) 합성 중...")
    cta_audio = _build_cta_audio(cta_text, job_dir)
    parts.append(cta_audio)
    segments.append({
        "cta":   {"start": CTA_START, "end": TOTAL_DURATION},
        "base":  CTA_START,
    })

    _concat(parts, output_path)
    actual = _get_duration(output_path)
    print(f"  [TTS] 에피소드 합성 완료: {output_path.name} ({actual:.1f}초 / 목표 {TOTAL_DURATION:.0f}s)")
    return output_path, segments
