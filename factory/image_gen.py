"""
오당역 — Image Generator
DALL-E 3 1차, 실패 시 Replicate Flux-schnell 폴백
시대별 배경 이미지 1장 생성 (1024x1792 세로형)
"""

import os
import subprocess
import time
from pathlib import Path

import requests
from openai import OpenAI

from config import (
    OPENAI_API_KEY,
    REPLICATE_API_TOKEN,
    REPLICATE_MODEL,
    IMAGE_BACKEND_PRIMARY,
    IMAGE_BACKEND_FALLBACK,
)


_STYLE_PREFIX = (
    "warm classic illustration, rich oil painting texture, timeless storybook art, "
    "natural warm color palette, gentle inviting atmosphere, detailed background, "
    "family-friendly, no violence, no gore, no text, no watermark, "
    "cinematic composition, vertical 9:16 portrait"
)

_ERA_SETTINGS: dict[str, str] = {
    "삼국": (
        "ancient Korean Three Kingdoms era (Goguryeo, Baekje, Silla, Gaya), "
        "stone fortress walls, traditional ancient Korean costume, "
        "mountain landscape with pine trees, golden hour lighting, "
        "NOT Chinese, NOT Japanese"
    ),
    "고려": (
        "Goryeo dynasty Korea (10~14th century), traditional Goryeo court hanbok, "
        "celadon pottery atmosphere, mist-covered mountains, warm golden lighting, "
        "NOT Joseon, NOT Chinese"
    ),
    "조선": (
        "Joseon dynasty Korea palace (Gyeongbokgung style), "
        "ornate curved rooftops with dancheong patterns, court hanbok with black gat, "
        "warm candlelight, traditional Korean garden"
    ),
    "근현대": (
        "late 19th to 20th century Korea, Korean Empire or colonial Seoul streetscape, "
        "mix of traditional hanok and early-modern western architecture, "
        "sepia-warm tones, historic photographs feel"
    ),
    "세계사": (
        "world history dramatic scene — ancient Rome forum OR medieval European castle OR "
        "Renaissance palazzo, warm Mediterranean or golden-hour lighting, "
        "NOT Korean, NOT East Asian"
    ),
}


def _build_prompt(era: str, extra: str = "") -> str:
    setting = _ERA_SETTINGS.get(era, _ERA_SETTINGS["조선"])
    extra_block = f", {extra}" if extra else ""
    return f"{_STYLE_PREFIX}, {setting}{extra_block}"


def _resize_to_vertical(src: Path, dst: Path, w: int = 1080, h: int = 1920) -> None:
    cmd = [
        "ffmpeg", "-y", "-i", str(src),
        "-vf", f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}",
        "-q:v", "2", str(dst),
    ]
    subprocess.run(cmd, capture_output=True, timeout=60)


def _dalle(prompt: str, out_path: Path) -> bool:
    if not OPENAI_API_KEY:
        return False
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        resp = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1792",
            quality="standard",
            n=1,
        )
        url = resp.data[0].url
        raw = out_path.with_suffix(".raw.png")
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        raw.write_bytes(r.content)
        _resize_to_vertical(raw, out_path)
        raw.unlink(missing_ok=True)
        return out_path.exists()
    except Exception as e:
        print(f"  [image] DALL-E 실패: {e}")
        return False


def _replicate(prompt: str, out_path: Path) -> bool:
    if not REPLICATE_API_TOKEN:
        return False
    try:
        import replicate
        os.environ["REPLICATE_API_TOKEN"] = REPLICATE_API_TOKEN
        output = replicate.run(
            REPLICATE_MODEL,
            input={
                "prompt": prompt,
                "aspect_ratio": "9:16",
                "num_outputs": 1,
                "output_format": "png",
            },
        )
        url = output[0] if isinstance(output, list) else output
        if hasattr(url, "read"):
            raw = out_path.with_suffix(".raw.png")
            raw.write_bytes(url.read())
        else:
            raw = out_path.with_suffix(".raw.png")
            r = requests.get(str(url), timeout=60)
            r.raise_for_status()
            raw.write_bytes(r.content)
        _resize_to_vertical(raw, out_path)
        raw.unlink(missing_ok=True)
        return out_path.exists()
    except Exception as e:
        print(f"  [image] Replicate 실패: {e}")
        return False


def generate_bg_image(era: str, out_path: Path, extra: str = "") -> Path | None:
    prompt = _build_prompt(era, extra)
    print(f"  [image] 시대={era} 배경 생성 시도...")

    backends = [IMAGE_BACKEND_PRIMARY, IMAGE_BACKEND_FALLBACK]
    for backend in backends:
        for attempt in range(2):
            ok = _dalle(prompt, out_path) if backend == "dalle" else _replicate(prompt, out_path)
            if ok:
                print(f"  [image] ✓ {backend} 성공 ({out_path.name})")
                return out_path
            if attempt == 0:
                time.sleep(2)
        print(f"  [image] {backend} 실패 → 다음 백엔드 시도")

    return None
