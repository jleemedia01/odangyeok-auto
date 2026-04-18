"""
오당역 — Background provider
퀴즈 시대(era)에 맞는 배경 이미지 1장 반환 (정적 이미지).
실패 시 그라디언트 폴백 이미지 생성.
"""

import subprocess
from pathlib import Path

from config import VIDEO_WIDTH, VIDEO_HEIGHT, ERA_COLORS
from image_gen import generate_bg_image


def _gradient_fallback(era: str, out_path: Path) -> Path:
    """FFmpeg lavfi 로 시대별 컬러 그라디언트 생성."""
    primary, accent = ERA_COLORS.get(era, ((40, 40, 80), (120, 120, 200)))
    c1 = "0x{:02x}{:02x}{:02x}".format(*primary)
    c2 = "0x{:02x}{:02x}{:02x}".format(*accent)
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", (
            f"color=c={c1}:size={VIDEO_WIDTH}x{VIDEO_HEIGHT}[a];"
            f"color=c={c2}:size={VIDEO_WIDTH}x{VIDEO_HEIGHT}[b];"
            f"[a][b]blend=all_mode=multiply"
        ),
        "-frames:v", "1",
        str(out_path),
    ]
    subprocess.run(cmd, capture_output=True, timeout=30)
    return out_path


def get_background(era: str, job_dir: Path) -> Path:
    job_dir.mkdir(parents=True, exist_ok=True)
    out = job_dir / "background.jpg"
    result = generate_bg_image(era, out)
    if result and result.exists():
        return result
    print(f"  [bg] 이미지 백엔드 전부 실패 → 그라디언트 폴백")
    return _gradient_fallback(era, out)
