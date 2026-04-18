"""
오당역 — Episode thumbnail (1280x720)
5문제 챌린지 컨셉: 상단 "5문제 챌린지" 배지 · 중앙 큰 훅 문구 · 하단 시대/난이도 라벨
"""

from pathlib import Path

from config import (
    THUMBNAIL_WIDTH,
    THUMBNAIL_HEIGHT,
    FONT_BOLD,
    FONT_REGULAR,
    ERA_COLORS,
    CHANNEL_NAME,
    NUM_QUIZZES,
)


def generate_episode_thumbnail(
    quizzes: list[dict],
    episode_meta: dict,
    output_path: Path,
    job_dir: Path,
    bg_path: Path | None = None,
) -> Path:
    try:
        from PIL import Image  # noqa: F401
        return _pillow_thumbnail(quizzes, episode_meta, output_path, job_dir, bg_path)
    except ImportError:
        print("  [썸네일] Pillow 없음 → 단색 폴백")
        return _ffmpeg_thumbnail(quizzes, output_path)


# ── 하위 호환 (단일 퀴즈) — villain-auto 스타일 유지 ───────────────────────────
def generate_thumbnail(quiz: dict, output_path: Path, job_dir: Path, bg_path: Path | None = None) -> Path:
    meta = {"thumbnail_text": quiz.get("thumbnail_text", "정답은?")}
    return generate_episode_thumbnail([quiz], meta, output_path, job_dir, bg_path)


def _load_font(path: str | None, size: int):
    from PIL import ImageFont
    if path:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    for fp in [
        "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    ]:
        try:
            return ImageFont.truetype(fp, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _pillow_thumbnail(
    quizzes: list[dict],
    episode_meta: dict,
    output_path: Path,
    job_dir: Path,
    bg_path: Path | None,
) -> Path:
    from PIL import Image, ImageDraw, ImageEnhance

    W, H = THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT
    first_era = quizzes[0].get("era", "조선") if quizzes else "조선"
    primary, accent = ERA_COLORS.get(first_era, ((40, 40, 80), (120, 120, 200)))

    # 1. 배경
    if bg_path and bg_path.exists() and bg_path.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
        img = Image.open(bg_path).convert("RGB").resize((W, H))
        img = ImageEnhance.Brightness(img).enhance(0.50)
        img = ImageEnhance.Contrast(img).enhance(1.3)
    else:
        img = _gradient(W, H, primary, accent)

    # 2. 암막 (상단 + 하단)
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for y in range(0, H // 3):
        alpha = int(180 * (1 - y / (H // 3)))
        od.line([(0, y), (W, y)], fill=(0, 0, 0, alpha))
    for y in range(H // 2, H):
        alpha = int(220 * (y - H // 2) / (H // 2))
        od.line([(0, y), (W, y)], fill=(0, 0, 0, alpha))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    draw = ImageDraw.Draw(img)

    font_badge_big = _load_font(FONT_BOLD, 64)
    font_badge_sm  = _load_font(FONT_BOLD, 38)
    font_main      = _load_font(FONT_BOLD, 96)
    font_era       = _load_font(FONT_REGULAR, 36)
    font_channel   = _load_font(FONT_REGULAR, 34)

    # 3. 상단 중앙 큰 "5문제 챌린지" 배지
    chall_text = f"🧠 {NUM_QUIZZES}문제 챌린지"
    try:
        bb = draw.textbbox((0, 0), chall_text, font=font_badge_big)
        bw, bh = bb[2] - bb[0] + 40, bb[3] - bb[1] + 22
    except Exception:
        bw, bh = len(chall_text) * 40 + 40, 90
    bx = (W - bw) // 2
    by = 36
    try:
        draw.rounded_rectangle([bx, by, bx + bw, by + bh], radius=18, fill=(220, 40, 60))
    except AttributeError:
        draw.rectangle([bx, by, bx + bw, by + bh], fill=(220, 40, 60))
    draw.text((bx + 20, by + 8), chall_text, fill=(255, 255, 255), font=font_badge_big)

    # 4. 상단 우측 카운트 표시 (원형으로 1-5)
    # 시각적 임팩트 — 간단히 생략하고 시대 라벨만
    era_list = ", ".join(episode_meta.get("eras", [])[:3])
    try:
        bb = draw.textbbox((0, 0), era_list, font=font_era)
        ew = bb[2] - bb[0]
    except Exception:
        ew = len(era_list) * 22
    draw.text((W - ew - 40, by + 10), era_list, fill=(255, 230, 80), font=font_era)

    # 5. 중앙/하단 큰 훅 문구
    hook_lines = [
        "5문제 다 맞히면",
        "당신도 역사퀴즈왕!",
    ]
    line_h = 120
    total_h = len(hook_lines) * line_h
    y_start = H // 2 - 20

    cx = W // 2
    for i, line in enumerate(hook_lines):
        y = y_start + i * line_h
        for dx in range(-4, 5):
            for dy in range(-4, 5):
                if abs(dx) + abs(dy) >= 4:
                    draw.text((cx + dx, y + dy), line, fill=(0, 0, 0), font=font_main, anchor="mm")
        color = (255, 255, 255) if i == 0 else (255, 230, 60)
        draw.text((cx, y), line, fill=color, font=font_main, anchor="mm")

    # 6. 채널명 최하단
    draw.text((cx, H - 30), CHANNEL_NAME, fill=(230, 230, 230), font=font_channel, anchor="mm")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path), "JPEG", quality=93)
    print(f"  [썸네일] 완료: {output_path.name}")
    return output_path


def _gradient(w: int, h: int, top: tuple, bottom: tuple):
    from PIL import Image
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        t = y / max(h - 1, 1)
        r = int(top[0] * (1 - t) + bottom[0] * t)
        g = int(top[1] * (1 - t) + bottom[1] * t)
        b = int(top[2] * (1 - t) + bottom[2] * t)
        for x in range(w):
            px[x, y] = (r, g, b)
    return img


def _ffmpeg_thumbnail(quizzes: list[dict], output_path: Path) -> Path:
    import subprocess
    first_era = quizzes[0].get("era", "조선") if quizzes else "조선"
    primary, _ = ERA_COLORS.get(first_era, ((40, 40, 80), (120, 120, 200)))
    color = "0x{:02x}{:02x}{:02x}".format(*primary)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"color=c={color}:size={THUMBNAIL_WIDTH}x{THUMBNAIL_HEIGHT}",
        "-frames:v", "1",
        str(output_path),
    ]
    subprocess.run(cmd, capture_output=True, timeout=30)
    return output_path
