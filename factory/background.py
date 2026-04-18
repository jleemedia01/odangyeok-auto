"""
오당역 — Background provider
퀴즈 시대(era)에 맞는 배경 이미지 1장 반환 (정적 이미지).

일 1이미지 캐시: KST 오늘 날짜 기준 assets/daily_bg/YYYYMMDD.jpg 가 있으면 재사용,
없으면 DALL-E 호출해서 캐시 생성. 하루 3편 업로드 중 1편만 실제 API 호출.
"""

import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from config import VIDEO_WIDTH, VIDEO_HEIGHT, ERA_COLORS, ASSETS_DIR
from image_gen import generate_bg_image

KST = timezone(timedelta(hours=9))
BG_CACHE_DIR = ASSETS_DIR / "daily_bg"


def _today_kst_key() -> str:
    return datetime.now(KST).strftime("%Y%m%d")


def _get_cached_bg() -> Path | None:
    BG_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached = BG_CACHE_DIR / f"{_today_kst_key()}.jpg"
    if cached.exists() and cached.stat().st_size > 10_000:
        return cached
    return None


def _save_to_cache(src: Path) -> Path:
    BG_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    dst = BG_CACHE_DIR / f"{_today_kst_key()}.jpg"
    shutil.copy(src, dst)
    return dst


def _prune_old_cache(keep_days: int = 30) -> None:
    """30일 지난 캐시 이미지 정리 (repo 용량 관리)."""
    if not BG_CACHE_DIR.exists():
        return
    cutoff = datetime.now(KST) - timedelta(days=keep_days)
    cutoff_key = cutoff.strftime("%Y%m%d")
    for p in BG_CACHE_DIR.glob("*.jpg"):
        if p.stem < cutoff_key:
            try:
                p.unlink()
                print(f"  [bg] 오래된 캐시 삭제: {p.name}")
            except Exception:
                pass


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

    # ── 1일 1이미지 캐시 조회 (KST 기준) ─────────────────────────────────────
    cached = _get_cached_bg()
    if cached:
        shutil.copy(cached, out)
        print(f"  [bg] ✓ 캐시 히트 — {cached.name} 재사용 (DALL-E 스킵, $0.08 절감)")
        return out

    # ── 캐시 미스: 새로 생성 + 캐시 저장 ────────────────────────────────────
    print(f"  [bg] 캐시 미스 — DALL-E 호출로 오늘 이미지 생성 ({_today_kst_key()})")
    result = generate_bg_image(era, out)
    if result and result.exists():
        cache_path = _save_to_cache(result)
        print(f"  [bg] 캐시 저장: {cache_path.name}")
        _prune_old_cache()
        return result
    print(f"  [bg] 이미지 백엔드 전부 실패 → 그라디언트 폴백 (캐시 안 됨)")
    return _gradient_fallback(era, out)
