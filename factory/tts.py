"""
오당역 — TTS (4-segment audio composer)
60초 쇼츠의 4개 구간 오디오를 생성·병합:
  1) 문제 (5s)   — OpenAI TTS 'nova', 길이 맞춰 패딩
  2) 카운트다운 (5s) — 무음 (영상 쪽에서 시각 효과)
  3) 정답 공개 (5s) — OpenAI TTS 'onyx'
  4) 해설 (45s) — OpenAI TTS 'shimmer', 속도 1.05

출력: 하나의 60초 MP3
"""

import json
import os
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
    TTS_SPEED_QUESTION,
    TTS_SPEED_EXPLAIN,
    SEG_QUESTION,
    SEG_COUNTDOWN,
    SEG_REVEAL,
    SEG_EXPLANATION,
    TOTAL_DURATION,
    AUDIO_BITRATE,
)


# ── 숫자 → 한국어 변환 ────────────────────────────────────────────────────────
def _convert_numbers_korean(text: str) -> str:
    def _chunk(n: int) -> str:
        if n == 0:
            return ""
        units = ["", "일", "이", "삼", "사", "오", "육", "칠", "팔", "구"]
        small = ["", "십", "백", "천"]
        out = ""
        for i in range(3, -1, -1):
            d = (n // (10 ** i)) % 10
            if d == 0:
                continue
            out += (small[i] if d == 1 and i > 0 else units[d] + small[i])
        return out

    def _to_ko(n: int) -> str:
        if n == 0:
            return "영"
        big = ["", "만", "억", "조"]
        out = ""
        for i in range(3, -1, -1):
            chunk = (n // (10000 ** i)) % 10000
            if chunk == 0:
                continue
            out += _chunk(chunk) + big[i]
        return out

    return re.sub(r"\d+", lambda m: _to_ko(int(m.group())), text)


def _get_duration(path: Path) -> float:
    try:
        r = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_format", str(path),
            ],
            capture_output=True, text=True, timeout=30,
        )
        return float(json.loads(r.stdout)["format"]["duration"])
    except Exception:
        return 0.0


def _clean_for_tts(text: str) -> str:
    t = re.sub(r"\*{1,3}(.+?)\*{1,3}", r"\1", text)
    t = re.sub(r"^#{1,6}\s+.*$", "", t, flags=re.MULTILINE)
    t = re.sub(r"\[.*?\]", "", t)
    return t.strip()


def _openai_tts(text: str, voice: str, speed: float, out_path: Path) -> None:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY 미설정")
    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.audio.speech.create(
        model=TTS_MODEL,
        voice=voice,
        input=text,
        speed=speed,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    response.stream_to_file(str(out_path))


def _silence(duration: float, out_path: Path) -> None:
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"anullsrc=r=44100:cl=mono",
        "-t", f"{duration:.3f}",
        "-c:a", "libmp3lame", "-b:a", AUDIO_BITRATE,
        str(out_path),
    ]
    subprocess.run(cmd, capture_output=True, timeout=30, check=True)


def _pad_or_trim(src: Path, target: float, out: Path) -> None:
    """src 오디오를 정확히 target초로 만들기 — 짧으면 끝에 무음 패딩, 길면 자름."""
    cmd = [
        "ffmpeg", "-y",
        "-i", str(src),
        "-af", f"apad=whole_dur={target:.3f}",
        "-t", f"{target:.3f}",
        "-c:a", "libmp3lame", "-b:a", AUDIO_BITRATE,
        str(out),
    ]
    subprocess.run(cmd, capture_output=True, timeout=60, check=True)


def _concat(segments: list[Path], out_path: Path) -> None:
    """ffmpeg concat demuxer로 MP3 이어붙이기."""
    list_file = out_path.with_suffix(".list.txt")
    list_file.write_text(
        "\n".join(f"file '{p.resolve()}'" for p in segments), encoding="utf-8"
    )
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(list_file),
        "-c:a", "libmp3lame", "-b:a", AUDIO_BITRATE,
        "-ar", "44100",
        str(out_path),
    ]
    subprocess.run(cmd, capture_output=True, timeout=120, check=True)
    list_file.unlink(missing_ok=True)


# ── 공개 API ──────────────────────────────────────────────────────────────────
def generate_quiz_tts(
    quiz: dict,
    output_path: Path,
    job_dir: Path,
) -> tuple[Path, dict]:
    """
    퀴즈 dict → 60초 TTS MP3 생성.
    반환: (output_path, segment_info)
    segment_info: 각 구간 시작/끝 시각 (렌더러·자막에서 사용)
    """
    q_text = _clean_for_tts(quiz["question"])
    if quiz["type"] == "4지선다":
        opts = quiz.get("options", [])
        q_text = q_text + " " + " ".join(
            f"{i+1}번, {o}." for i, o in enumerate(opts)
        )

    # 정답 공개 멘트
    if quiz["type"] == "OX":
        reveal_text = f"정답은 {quiz['answer']}!"
    else:
        ans_idx = int(quiz["answer"]) - 1
        opts = quiz.get("options", [])
        ans_text = opts[ans_idx] if 0 <= ans_idx < len(opts) else ""
        reveal_text = f"정답은 {quiz['answer']}번, {ans_text}!"

    explain_text = _convert_numbers_korean(_clean_for_tts(quiz["explanation"]))
    q_text       = _convert_numbers_korean(q_text)
    reveal_text  = _convert_numbers_korean(reveal_text)

    job_dir.mkdir(parents=True, exist_ok=True)

    # 1) 문제 음성 (생성 → 5초 패딩/트림)
    q_raw = job_dir / "seg_question_raw.mp3"
    q_out = job_dir / "seg_question.mp3"
    _openai_tts(q_text, TTS_VOICE_QUESTION, TTS_SPEED_QUESTION, q_raw)
    _pad_or_trim(q_raw, SEG_QUESTION, q_out)

    # 2) 카운트다운 — 무음 (영상 쪽에서 숫자 + 비프 처리)
    cd_out = job_dir / "seg_countdown.mp3"
    _silence(SEG_COUNTDOWN, cd_out)

    # 3) 정답 공개
    r_raw = job_dir / "seg_reveal_raw.mp3"
    r_out = job_dir / "seg_reveal.mp3"
    _openai_tts(reveal_text, TTS_VOICE_REVEAL, 1.0, r_raw)
    _pad_or_trim(r_raw, SEG_REVEAL, r_out)

    # 4) 해설 (45초 — 속도 1.05로 여유)
    e_raw = job_dir / "seg_explain_raw.mp3"
    e_out = job_dir / "seg_explain.mp3"
    _openai_tts(explain_text, TTS_VOICE_EXPLAIN, TTS_SPEED_EXPLAIN, e_raw)
    _pad_or_trim(e_raw, SEG_EXPLANATION, e_out)

    # 병합 (무조건 60초)
    _concat([q_out, cd_out, r_out, e_out], output_path)

    # 임시 파일 정리
    for p in [q_raw, r_raw, e_raw]:
        p.unlink(missing_ok=True)

    actual = _get_duration(output_path)
    print(f"  [TTS] 4-segment 합성 완료: {output_path.name} ({actual:.1f}초)")

    segments = {
        "question":    {"start": 0.0,                                       "end": SEG_QUESTION},
        "countdown":   {"start": SEG_QUESTION,                              "end": SEG_QUESTION + SEG_COUNTDOWN},
        "reveal":      {"start": SEG_QUESTION + SEG_COUNTDOWN,              "end": SEG_QUESTION + SEG_COUNTDOWN + SEG_REVEAL},
        "explanation": {"start": SEG_QUESTION + SEG_COUNTDOWN + SEG_REVEAL, "end": TOTAL_DURATION},
        "total":       TOTAL_DURATION,
        "explain_text": explain_text,   # 자막 생성용
        "question_text": q_text,
        "reveal_text": reveal_text,
    }
    return output_path, segments
