"""
오당역 — Channel icon generator (one-shot)
DALL-E 3로 YouTube 채널 프로필 아이콘을 1024x1024 로 생성.

사용:
  export OPENAI_API_KEY='sk-...'
  python scripts/generate_channel_icon.py

출력:
  assets/channel_icon.png   (1024x1024 원본)
  assets/channel_icon_800.png (800x800 YouTube 업로드용 — Pillow 가 있을 때)
"""

import os
import sys
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).parent.parent
OUT_PATH  = REPO_ROOT / "assets" / "channel_icon.png"
OUT_800   = REPO_ROOT / "assets" / "channel_icon_800.png"

PROMPT = (
    "Adorable mascot character for a Korean history quiz YouTube channel. "
    "ABSOLUTELY NO TEXT, NO LETTERS, NO HANGUL, NO CHARACTERS of any kind — "
    "zero typography in the image. "
    "\n\n"
    "MAIN CHARACTER: A super cute chibi-style mascot (1:2 head-to-body proportions) "
    "wearing a shiny gold royal five-point crown on top of the head. "
    "The character is flexing BOTH arms in a classic strongman 'show off the muscles' pose — "
    "both arms bent at elbows, fists up near the shoulders, small rounded biceps visible and proudly displayed. "
    "Confident proud happy expression, big sparkly round eyes, chubby cheeks, small cheerful smile. "
    "Round head, simple friendly body. "
    "\n\n"
    "STYLE: Modern flat vector illustration. Clean bold outlines. Kawaii/chibi aesthetic. "
    "Vibrant cheerful colors, warm and friendly. "
    "Think modern Korean YouTube mascot, LINE Friends style meets game-show mascot. "
    "Solid circular background (warm royal blue or deep navy) with a clean thin gold ring border. "
    "Character fills roughly 70% of the circle, well-centered. "
    "\n\n"
    "STRICTLY FORBIDDEN: no text, no hangul, no letters, no religious symbols, "
    "no yin-yang, no lotus, no halos, no mandala, no realistic proportions, "
    "no scary/serious expressions. "
    "\n\n"
    "Mood: energetic, playful, premium, highly memorable at small profile-picture sizes. "
    "The character should look strong-but-cute, like a tiny history quiz king flexing his brain power through his arms."
)


def main() -> int:
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        print("[오류] OPENAI_API_KEY 환경변수가 없습니다.", file=sys.stderr)
        return 1

    try:
        from openai import OpenAI
    except ImportError:
        print("[오류] pip install openai 먼저 실행하세요.", file=sys.stderr)
        return 1

    print("[아이콘] DALL-E 3 생성 중... (1024x1024)")
    client = OpenAI(api_key=api_key)
    resp = client.images.generate(
        model="dall-e-3",
        prompt=PROMPT,
        size="1024x1024",
        quality="hd",
        style="vivid",
        n=1,
    )
    url = resp.data[0].url
    if resp.data[0].revised_prompt:
        print(f"[아이콘] revised_prompt: {resp.data[0].revised_prompt[:140]}...")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    r = requests.get(url, timeout=90)
    r.raise_for_status()
    OUT_PATH.write_bytes(r.content)
    print(f"[아이콘] ✓ 저장: {OUT_PATH} ({OUT_PATH.stat().st_size/1024:.0f} KB)")

    # 800x800 리사이즈 (YouTube 권장 업로드 크기)
    try:
        from PIL import Image
        img = Image.open(OUT_PATH).convert("RGB")
        img.resize((800, 800), Image.LANCZOS).save(OUT_800, "PNG", optimize=True)
        print(f"[아이콘] ✓ 저장(800x800): {OUT_800}")
    except ImportError:
        print("[아이콘] Pillow 없어 800x800 리사이즈 스킵")

    print()
    print("YouTube Studio → 설정 → 채널 → 브랜딩 → 사진 업로드 에 위 파일 사용.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
