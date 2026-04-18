"""
오당역 — Thumbnail Generator (1280x720)
구성: 시대 배지 · 질문 텍스트 대형 · "정답은?" 훅 · 채널명
"""

from pathlib import Path

from config import (
    THUMBNAIL_WIDTH,
    THUMBNAIL_HEIGHT,
    FONT_BOLD,
    FONT_REGULAR,
    ERA_COLORS,
    CHANNEL_NAME,
)


def generate_thumbnail(
    quiz: dict,
    output_path: Path,
    job_dir: Path,
    bg_path: Path | None = None,
) -> Path:
    try:
        from PIL import Image
        return _pillow_thumbnail(quiz, output_path, job_dir, bg_path)
    except ImportError:
        print("  [썸네일] Pillow 없음 → 단색 폴백")
        return _ffmpeg_thumbnail(quiz, output_path)


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


def _wrap(text: str, font, max_width: int, draw) -> list[str]:
    words = text.split()
    if not words:
        return [text]
    lines, current = [], []
    for w in words:
        test = " ".join(current + [w])
        try:
            bb = draw.textbbox((0, 0), test, font=font)
            width = bb[2] - bb[0]
        except Exception:
            width = len(test) * 40
        if width > max_width and current:
            lines.append(" ".join(current))
            current = [w]
        else:
            current.append(w)
    if current:
        lines.append(" ".join(current))
    return lines


def _pillow_thumbnail(
    quiz: dict,
    output_path: Path,
    job_dir: Path,
    bg_path: Path | None,
) -> Path:
    from PIL import Image, ImageDraw, ImageEnhance

    W, H = THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT
    era  = quiz.get("era", "조선")
    primary, accent = ERA_COLORS.get(era, ((40, 40, 80), (120, 120, 200)))

    # ── 1. 배경 ───────────────────────────────────────────────────────────
    if bg_path and bg_path.exists() and bg_path.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
        img = Image.open(bg_path).convert("RGB").resize((W, H))
        img = ImageEnhance.Brightness(img).enhance(0.55)
        img = ImageEnhance.Contrast(img).enhance(1.25)
    else:
        img = _gradient(W, H, primary, accent)

    # ── 2. 하단 암막 (가독성) ─────────────────────────────────────────────
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for y in range(H // 2, H):
        alpha = int(210 * (y - H // 2) / (H // 2))
        od.line([(0, y), (W, y)], fill=(0, 0, 0, alpha))
    for y in range(0, H // 4):
        alpha = int(160 * (1 - y / (H // 4)))
        od.line([(0, y), (W, y)], fill=(0, 0, 0, alpha))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    draw = ImageDraw.Draw(img)

    font_badge   = _load_font(FONT_BOLD, 40)
    font_hook    = _load_font(FONT_BOLD, 72)
    font_q       = _load_font(FONT_BOLD, 88)
    font_channel = _load_font(FONT_REGULAR, 34)

    # ── 3. 상단 시대 배지 ────────────────────────────────────────────────
    badge_text = f"  {era}  "
    try:
        bb = draw.textbbox((0, 0), badge_text, font=font_badge)
        bw, bh = bb[2] - bb[0] + 30, bb[3] - bb[1] + 22
    except Exception:
        bw, bh = len(badge_text) * 26 + 30, 64
    bx, by = 40, 40
    try:
        draw.rounded_rectangle([bx, by, bx + bw, by + bh], radius=14, fill=primary)
    except AttributeError:
        draw.rectangle([bx, by, bx + bw, by + bh], fill=primary)
    draw.text((bx + 15, by + 10), badge_text.strip(), fill=(255, 255, 255), font=font_badge)

    # ── 4. 훅 (상단 우측) ────────────────────────────────────────────────
    hook = quiz.get("thumbnail_text") or "정답은?"
    try:
        bb = draw.textbbox((0, 0), hook, font=font_hook)
        hw = bb[2] - bb[0]
    except Exception:
        hw = len(hook) * 48
    hx = W - hw - 50
    hy = 50
    # 그림자
    for dx in range(-3, 4):
        for dy in range(-3, 4):
            if abs(dx) + abs(dy) >= 3:
                draw.text((hx + dx, hy + dy), hook, fill=(0, 0, 0), font=font_hook)
    draw.text((hx, hy), hook, fill=(255, 230, 60), font=font_hook)

    # ── 5. 중앙·하단 질문 ────────────────────────────────────────────────
    q = quiz["question"]
    lines = _wrap(q, font_q, W - 120, draw)
    line_h = 110
    total_h = len(lines) * line_h
    y_start = H - total_h - 120

    cx = W // 2
    for i, line in enumerate(lines):
        y = y_start + i * line_h
        for dx in range(-4, 5):
            for dy in range(-4, 5):
                if abs(dx) + abs(dy) >= 4:
                    draw.text((cx + dx, y + dy), line, fill=(0, 0, 0), font=font_q, anchor="mm")
        draw.text((cx, y), line, fill=(255, 255, 255), font=font_q, anchor="mm")

    # ── 6. 채널명 (최하단) ───────────────────────────────────────────────
    draw.text((cx, H - 28), f"{CHANNEL_NAME}", fill=(230, 230, 230), font=font_channel, anchor="mm")

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


def _ffmpeg_thumbnail(quiz: dict, output_path: Path) -> Path:
    import subprocess
    output_path.parent.mkdir(parents=True, exist_ok=True)
    era = quiz.get("era", "조선")
    primary, _ = ERA_COLORS.get(era, ((40, 40, 80), (120, 120, 200)))
    color = "0x{:02x}{:02x}{:02x}".format(*primary)
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"color=c={color}:size={THUMBNAIL_WIDTH}x{THUMBNAIL_HEIGHT}",
        "-frames:v", "1",
        str(output_path),
    ]
    subprocess.run(cmd, capture_output=True, timeout=30)
    return output_path
