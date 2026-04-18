"""
오당역 — Episode subtitles (5 quizzes × 24s = 120s)
각 퀴즈의 4구간 오버레이를 모두 포함한 단일 ASS.

문제 번호 배지 ("1/5" 등)는 매 퀴즈 전체 24s 동안 상단 좌측에 고정 표시.
"""

import re
from pathlib import Path

from config import (
    SUBTITLE_FONT,
    SUBTITLE_FONT_SIZE,
    SUBTITLE_OUTLINE,
    SUBTITLE_SHADOW,
    SEG_QUESTION,
    SEG_COUNTDOWN,
    SEG_REVEAL,
    SEG_CTA,
    QUIZ_DURATION,
    CTA_START,
    TOTAL_DURATION,
)

_MAX_CHARS_PER_LINE = 11


def _fmt(sec: float) -> str:
    h  = int(sec // 3600)
    m  = int((sec % 3600) // 60)
    s  = int(sec % 60)
    cs = int((sec % 1) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _split_chunks(text: str) -> list[str]:
    sents = re.split(r"(?<=[.!?。])\s*", text.strip())
    sents = [s.strip() for s in sents if s.strip()]
    chunks: list[str] = []
    for s in sents:
        while len(s) > _MAX_CHARS_PER_LINE:
            cut = _MAX_CHARS_PER_LINE
            for sep in [",", " ", "、"]:
                idx = s.rfind(sep, 0, _MAX_CHARS_PER_LINE + 1)
                if idx > 0:
                    cut = idx + 1
                    break
            chunks.append(s[:cut].strip())
            s = s[cut:].strip()
        if s:
            chunks.append(s)
    return chunks


def _explanation_timings(text: str, start: float, end: float) -> list[tuple[float, float, str]]:
    chunks = _split_chunks(text)
    if not chunks:
        return []
    char_counts = [max(len(c.replace(" ", "")), 1) for c in chunks]
    total = sum(char_counts)
    span = max(end - start - 0.2, 0.6)
    out: list[tuple[float, float, str]] = []
    t = start + 0.05
    for i, (c, n) in enumerate(zip(chunks, char_counts)):
        dur = max(0.35, min(3.5, (n / total) * span))
        te  = t + dur if i < len(chunks) - 1 else end - 0.05
        out.append((t, te, c))
        t = te
    return out


def _ass_header() -> str:
    return (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 1080\n"
        "PlayResY: 1920\n"
        "ScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        # 질문 — 상단, 노란색
        f"Style: Q_BIG,{SUBTITLE_FONT},84,"
        f"&H0000E5FF,&H000000FF,&H00000000,&H00000000,"
        f"-1,0,0,0,100,100,0,0,1,{SUBTITLE_OUTLINE},{SUBTITLE_SHADOW},"
        f"8,60,60,280,1\n"
        # 4지선다 보기 — 중단 (\pos 로 수동 배치)
        f"Style: Q_OPT,{SUBTITLE_FONT},70,"
        f"&H00FFFFFF,&H000000FF,&H00000000,&H00000000,"
        f"-1,0,0,0,100,100,0,0,1,{SUBTITLE_OUTLINE},{SUBTITLE_SHADOW},"
        f"5,80,80,0,1\n"
        # 카운트다운 숫자 (초대형, 중앙)
        f"Style: CD,{SUBTITLE_FONT},520,"
        f"&H0000FFFF,&H000000FF,&H00000000,&H00000000,"
        f"-1,0,0,0,100,100,0,0,1,14,0,"
        f"5,0,0,0,1\n"
        # 정답 하이라이트 (녹색, 초대형 중앙)
        f"Style: REVEAL,{SUBTITLE_FONT},200,"
        f"&H0000FF00,&H000000FF,&H00000000,&H00000000,"
        f"-1,0,0,0,100,100,0,0,1,14,0,"
        f"5,0,0,0,1\n"
        # 해설 자막 — 하단
        f"Style: EXP,{SUBTITLE_FONT},{SUBTITLE_FONT_SIZE},"
        f"&H00FFFFFF,&H000000FF,&H00000000,&H00000000,"
        f"-1,0,0,0,100,100,0,0,1,{SUBTITLE_OUTLINE},{SUBTITLE_SHADOW},"
        f"2,60,60,260,1\n"
        # 문제 번호 배지 — 상단 좌측 소형
        f"Style: NUM,{SUBTITLE_FONT},56,"
        f"&H00FFFFFF,&H000000FF,&H00000000,&H00000000,"
        f"-1,0,0,0,100,100,0,0,1,{SUBTITLE_OUTLINE},{SUBTITLE_SHADOW},"
        f"7,60,60,60,1\n"
        # CTA 타이틀 — 큰 노란색 (상단)
        f"Style: CTA_H,{SUBTITLE_FONT},120,"
        f"&H0000E5FF,&H000000FF,&H00000000,&H00000000,"
        f"-1,0,0,0,100,100,0,0,1,12,0,"
        f"8,60,60,320,1\n"
        # CTA 본문 자막 — 중앙 하단
        f"Style: CTA_B,{SUBTITLE_FONT},70,"
        f"&H00FFFFFF,&H000000FF,&H00000000,&H00000000,"
        f"-1,0,0,0,100,100,0,0,1,{SUBTITLE_OUTLINE},{SUBTITLE_SHADOW},"
        f"2,60,60,320,1\n"
        # 구독 배지 — 큰 빨간 박스 (중앙)
        f"Style: CTA_SUB,{SUBTITLE_FONT},90,"
        f"&H00FFFFFF,&H000000FF,&H0000003C,&H0000003C,"
        f"-1,0,0,0,100,100,0,0,3,12,0,"
        f"5,0,0,0,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )


def _dlg(style: str, start: float, end: float, text: str, inline: str = "") -> str:
    safe = text.replace(",", "，")
    body = f"{inline}{safe}" if inline else safe
    return f"Dialogue: 0,{_fmt(start)},{_fmt(end)},{style},,0,0,0,,{body}\n"


def _quiz_events(quiz: dict, idx: int, total: int) -> str:
    """한 퀴즈의 모든 Dialogue 라인 (base 시각 오프셋 포함)."""
    base = idx * QUIZ_DURATION
    out = ""

    # ── 문제 번호 배지 (전체 24s 고정) ─────────────────────────────────────
    out += _dlg("NUM", base, base + QUIZ_DURATION, f"문제 {idx+1}/{total}")

    # ── 질문 구간 (Q_BIG + 4지선다 보기) ────────────────────────────────────
    q_end = base + SEG_QUESTION
    out += _dlg("Q_BIG", base, q_end, quiz["question"])

    if quiz["type"] == "4지선다":
        labels = ["①", "②", "③", "④"]
        opts = quiz.get("options", [])
        for i, opt in enumerate(opts[:4]):
            y = 840 + i * 100
            out += (
                f"Dialogue: 0,{_fmt(base + 0.3)},{_fmt(q_end)},Q_OPT,,0,0,0,,"
                f"{{\\pos(540,{y})}}{labels[i]} {opt}\n"
            )

    # ── 카운트다운 (3, 2, 1 — 각 1초) ───────────────────────────────────────
    cd_base = base + SEG_QUESTION
    for i, digit in enumerate([3, 2, 1]):
        s = cd_base + i
        e = s + 1.0
        # 마지막 "1" 은 빨간색 + 커졌다 작아지는 펄스
        if digit == 1:
            out += (
                f"Dialogue: 0,{_fmt(s)},{_fmt(e)},CD,,0,0,0,,"
                f"{{\\c&H0000FF&\\fscx120\\fscy120\\t(0,300,\\fscx100\\fscy100)}}{digit}\n"
            )
        else:
            out += _dlg("CD", s, e, str(digit))

    # ── 정답 공개 ────────────────────────────────────────────────────────────
    rev_start = cd_base + SEG_COUNTDOWN
    rev_end   = rev_start + SEG_REVEAL
    reveal_text = quiz["answer"] if quiz["type"] == "OX" else f"{quiz['answer']}번"
    out += _dlg("REVEAL", rev_start, rev_end, reveal_text,
                inline="{\\fscx80\\fscy80\\t(0,250,\\fscx100\\fscy100)}")

    # ── 해설 ────────────────────────────────────────────────────────────────
    exp_start = rev_end
    exp_end   = base + QUIZ_DURATION
    for s, e, t in _explanation_timings(quiz["explanation"], exp_start, exp_end):
        out += _dlg("EXP", s, e, t)

    return out


def _cta_events(cta_text: str) -> str:
    """아웃트로 12s CTA 자막. 배지 3개는 renderer drawtext 가 담당 —
    여기선 하단 TTS 본문 자막만 표시. 상단은 채널 헤더가 차지해 CTA_H 미사용."""
    out = ""
    chunks = _split_chunks(cta_text)
    if chunks:
        char_counts = [max(len(c.replace(" ", "")), 1) for c in chunks]
        total_chars = sum(char_counts)
        span = max(SEG_CTA - 0.5, 1.0)
        t_cur = CTA_START + 0.2
        for i, (c, n) in enumerate(zip(chunks, char_counts)):
            dur = max(0.4, min(4.0, (n / total_chars) * span))
            te  = t_cur + dur if i < len(chunks) - 1 else TOTAL_DURATION - 0.2
            out += _dlg("CTA_B", t_cur, te, c)
            t_cur = te
    return out


def generate_episode_subtitles(
    quizzes: list[dict],
    output_path: Path,
    cta_text: str = "",
) -> Path:
    ass = _ass_header()
    for i, q in enumerate(quizzes):
        ass += _quiz_events(q, i, len(quizzes))
    if cta_text:
        ass += _cta_events(cta_text)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(ass, encoding="utf-8")
    print(f"  [subs] 에피소드 ASS 생성 완료: {output_path.name} ({len(quizzes)}문제 + CTA)")
    return output_path


# ── 하위 호환 (단일) ──────────────────────────────────────────────────────────
def generate_subtitles(quiz: dict, output_path: Path) -> Path:
    return generate_episode_subtitles([quiz], output_path)
