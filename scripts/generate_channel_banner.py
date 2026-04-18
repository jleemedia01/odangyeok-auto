"""
오당역 — Channel banner generator
DALL-E 3 로 배너 배경(1792×1024) 생성 → Pillow 로 2560×1440 업스케일 + 텍스트 오버레이.

YouTube 채널 배너 규격:
- 권장 업로드: 2560 × 1440
- 모든 기기 안전 영역: 1546 × 423 (중앙) — 텍스트는 이 안에 배치

사용:
  export OPENAI_API_KEY='sk-...'
  python scripts/generate_channel_banner.py
"""

import os
import sys
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

REPO_ROOT  = Path(__file__).parent.parent
OUT_2560   = REPO_ROOT / "assets" / "channel_banner_2560.png"
OUT_RAW    = REPO_ROOT / "assets" / "channel_banner_raw_1792.png"

BANNER_W, BANNER_H = 2560, 1440
# 안전 영역 (모든 기기에서 보이는 중앙 영역)
SAFE_W, SAFE_H = 1546, 423

PROMPT = (
    "Wide cinematic YouTube channel banner background for a Korean history quiz channel. "
    "Landscape format. ABSOLUTELY NO TEXT, NO LETTERS, NO HANGUL, NO CHARACTERS of any kind. "
    "\n\n"
    "COMPOSITION: Center area mostly clean and empty (for text to be added later). "
    "Decorative elements are arranged on the LEFT and RIGHT thirds of the image only — "
    "the middle 40% horizontal strip must be a clean dark gradient with minimal detail. "
    "\n\n"
    "BACKGROUND: Deep royal blue to navy radial gradient, rich and premium, "
    "with subtle warm glow in the center. "
    "\n\n"
    "DECORATIVE ELEMENTS (on left and right sides only): "
    "floating golden crowns with red jewels; "
    "ancient open scroll icons; golden question-mark symbols with sparkles; "
    "abstract stack-of-books silhouettes with gold accents; "
    "gold stars and soft sparkle particles; "
    "subtle Korean royal ornament patterns in gold line art. "
    "\n\n"
    "STYLE: Modern flat vector illustration, clean bold shapes, vibrant royal colors, "
    "premium TV game-show opening aesthetic meets educational channel. "
    "Palette: deep navy/royal blue background, warm gold accents, crimson red highlights, "
    "bright white sparkles. High contrast, crisp edges. "
    "\n\n"
    "STRICTLY FORBIDDEN: text / letters / hangul / alphabet / numbers, "
    "human figures, religious symbols (no yin-yang, no lotus, no halos, no mandala), "
    "realistic photography, dull colors."
)

CHANNEL_MAIN    = "오당역"
CHANNEL_TAG     = "오! 당신은 역사퀴즈왕"
CHANNEL_FOOTER  = "매일 3회 업로드  •  역사퀴즈 5문제 챌린지"


def _find_font(sizes_candidates: list[int], weight: str = "bold") -> list[ImageFont.FreeTypeFont]:
    bold_candidates = [
        "/usr/share/fonts/truetype/nanum/NanumGothicExtraBold.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    ]
    reg_candidates = [
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    ]
    paths = bold_candidates if weight == "bold" else reg_candidates
    font_path = next((p for p in paths if Path(p).exists()), None)
    if not font_path:
        return [ImageFont.load_default() for _ in sizes_candidates]
    return [ImageFont.truetype(font_path, s) for s in sizes_candidates]


def _generate_dalle(prompt: str, out_path: Path) -> None:
    from openai import OpenAI
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        sys.exit("[오류] OPENAI_API_KEY 미설정")
    print("[배너] DALL-E 3 생성 중 (1792×1024 HD)...")
    client = OpenAI(api_key=api_key)
    resp = client.images.generate(
        model="dall-e-3",
        prompt=prompt,
        size="1792x1024",
        quality="hd",
        style="vivid",
        n=1,
    )
    url = resp.data[0].url
    if resp.data[0].revised_prompt:
        print(f"[배너] revised_prompt: {resp.data[0].revised_prompt[:160]}...")
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(r.content)
    print(f"[배너] ✓ 원본 저장: {out_path}")


def _draw_text_with_outline(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int],
    outline: tuple[int, int, int],
    outline_w: int,
    anchor: str = "mm",
) -> None:
    x, y = xy
    for dx in range(-outline_w, outline_w + 1):
        for dy in range(-outline_w, outline_w + 1):
            if abs(dx) + abs(dy) >= outline_w:
                draw.text((x + dx, y + dy), text, font=font, fill=outline, anchor=anchor)
    draw.text(xy, text, font=font, fill=fill, anchor=anchor)


def _compose_banner(raw: Path, out: Path) -> None:
    print("[배너] 2560×1440 업스케일 + 텍스트 오버레이...")
    img = Image.open(raw).convert("RGB")

    # 업스케일 (1792×1024 → 2560×1440, 동일 16:9 → Lanczos로 부드럽게)
    img = img.resize((BANNER_W, BANNER_H), Image.LANCZOS)

    # 중앙 safe area 가독성용 살짝 어두운 오버레이
    overlay = Image.new("RGBA", (BANNER_W, BANNER_H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    cx, cy = BANNER_W // 2, BANNER_H // 2
    sx0, sy0 = cx - SAFE_W // 2, cy - SAFE_H // 2
    sx1, sy1 = cx + SAFE_W // 2, cy + SAFE_H // 2
    # 부드러운 가운데 암막 (radial feel — rounded rectangle with alpha)
    od.rounded_rectangle([sx0 - 40, sy0 - 30, sx1 + 40, sy1 + 30], radius=30, fill=(0, 0, 10, 95))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    draw = ImageDraw.Draw(img)

    # 폰트 로드
    font_main, font_tag, font_footer = _find_font([190, 92, 54])

    # 메인 텍스트 "오당역" — 금색 + 검은 외곽선
    main_y = cy - 80
    _draw_text_with_outline(
        draw, (cx, main_y), CHANNEL_MAIN, font_main,
        fill=(255, 215, 80), outline=(0, 0, 0), outline_w=8, anchor="mm",
    )

    # 태그라인 "오! 당신은 역사퀴즈왕" — 화이트 + 외곽선
    tag_y = main_y + 150
    _draw_text_with_outline(
        draw, (cx, tag_y), CHANNEL_TAG, font_tag,
        fill=(255, 255, 255), outline=(0, 0, 0), outline_w=5, anchor="mm",
    )

    # 푸터 "매일 3회 업로드 • 5문제 챌린지" — 연한 금색
    footer_y = tag_y + 100
    _draw_text_with_outline(
        draw, (cx, footer_y), CHANNEL_FOOTER, font_footer,
        fill=(255, 230, 150), outline=(0, 0, 0), outline_w=4, anchor="mm",
    )

    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "PNG", optimize=True)
    print(f"[배너] ✓ 최종 저장: {out} ({out.stat().st_size/1024:.0f} KB)")


def main() -> int:
    _generate_dalle(PROMPT, OUT_RAW)
    _compose_banner(OUT_RAW, OUT_2560)
    print()
    print("YouTube Studio → 설정 → 채널 → 브랜딩 → 배너 이미지 업로드 에 위 파일 사용.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
