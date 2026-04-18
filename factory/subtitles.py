"""
오당역 — Segment-aware subtitles (ASS)
4개 구간별로 화면에 다른 오버레이:
  - question (0~5s):    큰 질문 텍스트 + (4지선다면) 보기 A/B/C/D
  - countdown (5~10s):  큰 숫자 5→4→3→2→1, 매 초
  - reveal (10~15s):    "정답: O / X / 3번" 큰 글씨 하이라이트
  - explanation (15~60s): 일반 자막 (1~2줄씩 싱크)
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
    span = max(end - start - 0.3, 1.0)
    out: list[tuple[float, float, str]] = []
    t = start + 0.1
    for i, (c, n) in enumerate(zip(chunks, char_counts)):
        dur = max(0.4, min(4.0, (n / total) * span))
        te  = t + dur if i < len(chunks) - 1 else end - 0.1
        out.append((t, te, c))
        t = te
    return out


def _ass_header() -> str:
    """
    4개 스타일:
      Q_BIG    — 질문 (상단 중앙, 아주 큼)
      Q_OPT    — 4지선다 보기 (중단 좌측 정렬)
      CD       — 카운트다운 숫자 (정중앙, 초대형)
      REVEAL   — 정답 하이라이트 (정중앙, 큼)
      EXP      — 해설 일반 자막 (하단)
    """
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
        # 질문 — 상단, 노란색 큰 글씨
        f"Style: Q_BIG,{SUBTITLE_FONT},92,"
        f"&H0000E5FF,&H000000FF,&H00000000,&H00000000,"
        f"-1,0,0,0,100,100,0,0,1,{SUBTITLE_OUTLINE},{SUBTITLE_SHADOW},"
        f"8,60,60,240,1\n"
        # 4지선다 보기 — 중단, 흰색
        f"Style: Q_OPT,{SUBTITLE_FONT},74,"
        f"&H00FFFFFF,&H000000FF,&H00000000,&H00000000,"
        f"-1,0,0,0,100,100,0,0,1,18,{SUBTITLE_SHADOW},"
        f"5,80,80,0,1\n"
        # 카운트다운 숫자 — 초대형, 중앙
        f"Style: CD,{SUBTITLE_FONT},480,"
        f"&H0000FFFF,&H000000FF,&H00000000,&H00000000,"
        f"-1,0,0,0,100,100,0,0,1,32,0,"
        f"5,0,0,0,1\n"
        # 정답 하이라이트
        f"Style: REVEAL,{SUBTITLE_FONT},180,"
        f"&H0000FF00,&H000000FF,&H00000000,&H00000000,"
        f"-1,0,0,0,100,100,0,0,1,32,0,"
        f"5,0,0,0,1\n"
        # 해설 자막 — 하단
        f"Style: EXP,{SUBTITLE_FONT},{SUBTITLE_FONT_SIZE},"
        f"&H00FFFFFF,&H000000FF,&H00000000,&H00000000,"
        f"-1,0,0,0,100,100,0,0,1,{SUBTITLE_OUTLINE},{SUBTITLE_SHADOW},"
        f"2,60,60,320,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )


def _dlg(style: str, start: float, end: float, text: str) -> str:
    safe = text.replace(",", "，")   # ASS dialogue 구분자 회피
    return f"Dialogue: 0,{_fmt(start)},{_fmt(end)},{style},,0,0,0,,{safe}\n"


def generate_subtitles(
    quiz: dict,
    output_path: Path,
) -> Path:
    """퀴즈 dict 로부터 4-segment 오버레이 ASS 작성."""
    ass = _ass_header()

    # ── 1. 질문 구간 (0 ~ 5s) ────────────────────────────────────────────────
    question = quiz["question"]
    ass += _dlg("Q_BIG", 0.0, SEG_QUESTION, question)

    if quiz["type"] == "4지선다":
        opts = quiz.get("options", [])
        labels = ["①", "②", "③", "④"]
        # 각 보기 한 줄씩 — 세로 배치 (MarginV 다르게)
        # ASS Alignment=5 (중앙 중간) + 수직 offset 은 \pos 사용
        for i, opt in enumerate(opts[:4]):
            line = f"{labels[i]} {opt}"
            # 중앙 좌측 정렬 대신 수직 분산 — \pos(x,y)
            y = 820 + i * 100
            ass += (
                f"Dialogue: 0,{_fmt(0.3)},{_fmt(SEG_QUESTION)},Q_OPT,,0,0,0,,"
                f"{{\\pos(540,{y})}}{line}\n"
            )

    # ── 2. 카운트다운 (5 ~ 10s) — 5,4,3,2,1 매 초 ────────────────────────────
    cd_start = SEG_QUESTION
    for i, digit in enumerate([5, 4, 3, 2, 1]):
        s = cd_start + i
        e = s + 1.0
        ass += _dlg("CD", s, e, str(digit))

    # ── 3. 정답 공개 (10 ~ 15s) ──────────────────────────────────────────────
    rev_start = SEG_QUESTION + SEG_COUNTDOWN
    rev_end   = rev_start + SEG_REVEAL
    if quiz["type"] == "OX":
        reveal_text = quiz["answer"]     # "O" or "X"
    else:
        reveal_text = f"{quiz['answer']}번"
    ass += _dlg("REVEAL", rev_start, rev_end, reveal_text)

    # ── 4. 해설 (15 ~ 60s) ───────────────────────────────────────────────────
    exp_start = rev_end
    exp_end   = TOTAL_DURATION
    for s, e, t in _explanation_timings(quiz["explanation"], exp_start, exp_end):
        ass += _dlg("EXP", s, e, t)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(ass, encoding="utf-8")
    print(f"  [subs] segment-aware ASS 생성 완료: {output_path.name}")
    return output_path
