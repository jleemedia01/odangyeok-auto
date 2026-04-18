"""
오당역 — BGM downloader
Pixabay Music API에서 퀴즈쇼 느낌 BGM 한 곡을 받아 assets/bgm_quiz.mp3 로 저장.
이미 파일이 있으면 (10KB 초과) 스킵.

환경변수:
  PIXABAY_API_KEY — Pixabay 무료 계정에서 발급

CC0 (No Rights Reserved) · 출처 표기 불필요한 트랙만 선호.
"""

import os
import random
import subprocess
import sys
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).parent.parent
ASSETS    = REPO_ROOT / "assets"
BGM_PATH  = ASSETS / "bgm_quiz.mp3"

# Pixabay는 무료 이미지 API만 공개되어 있어 음악은 별도 방법 필요.
# 여기서는 안정적인 CC0 / public-domain 음악 제공자(Kevin MacLeod - incompetech,
# Free Music Archive 등) 의 직접 URL 중 퀴즈쇼 느낌 트랙을 후보로 시도.
# 최종 실패 시 assets/ 에 사용자가 직접 넣은 파일을 활용할 수 있도록 exit 코드만 다르게.

_FALLBACK_URLS = [
    # Kevin MacLeod — "The Builder" (CC BY 4.0 — 출처 표기로 사용 가능)
    "https://incompetech.com/music/royalty-free/mp3-royaltyfree/The%20Builder.mp3",
    # Kevin MacLeod — "Fluffing a Duck" (CC BY 4.0 — 퀴즈쇼·유쾌)
    "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Fluffing%20a%20Duck.mp3",
    # Kevin MacLeod — "Carefree" (CC BY 4.0 — 경쾌)
    "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Carefree.mp3",
]


def _already_ok() -> bool:
    return BGM_PATH.exists() and BGM_PATH.stat().st_size > 10_000


def _download(url: str, out: Path) -> bool:
    try:
        print(f"  [bgm] 다운로드 시도: {url}")
        r = requests.get(url, timeout=60, stream=True, headers={
            "User-Agent": "Mozilla/5.0 (odangyeok-auto bgm fetch)",
        })
        r.raise_for_status()
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        if out.stat().st_size > 10_000:
            print(f"  [bgm] ✓ 저장: {out} ({out.stat().st_size/1024:.0f} KB)")
            return True
        out.unlink(missing_ok=True)
    except Exception as e:
        print(f"  [bgm] 실패: {e}")
    return False


def _pixabay_search() -> "str | None":
    """Pixabay 이미지 API는 공개되지만 음악 API는 공식이 없음 — 스킵."""
    api_key = os.environ.get("PIXABAY_API_KEY", "")
    if not api_key:
        return None
    # Pixabay 음악 API 엔드포인트는 공개되어 있지 않아, 검색만 수행하고 실패 처리.
    return None


def main() -> int:
    if _already_ok():
        print(f"  [bgm] 이미 존재 — 스킵 ({BGM_PATH}, {BGM_PATH.stat().st_size/1024:.0f} KB)")
        return 0

    # 1) Pixabay 시도 (실제로는 음악 API 미지원이라 대부분 None)
    _ = _pixabay_search()

    # 2) 하드코딩된 fallback URL 순회
    urls = list(_FALLBACK_URLS)
    random.shuffle(urls)
    for url in urls:
        if _download(url, BGM_PATH):
            return 0

    print("  [bgm] 모든 소스 실패 — BGM 없이 진행 (렌더러가 자동으로 무음 처리)")
    return 0  # 실패해도 파이프라인은 계속 진행


if __name__ == "__main__":
    sys.exit(main())
