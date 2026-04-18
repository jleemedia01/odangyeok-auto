"""
오당역 — CI Entrypoint
GitHub Actions 에서 호출되는 진입점.
"""

import base64
import json
import os
import sys
import traceback
from pathlib import Path


def safe_print(*args, **kwargs):
    try:
        print(*args, **kwargs, flush=True)
    except (ValueError, OSError):
        pass


FACTORY_DIR = Path(__file__).parent
REPO_ROOT   = FACTORY_DIR.parent
sys.path.insert(0, str(FACTORY_DIR))


def validate_env() -> list[str]:
    required = ["OPENAI_API_KEY"]
    optional = ["REPLICATE_API_TOKEN", "YOUTUBE_API_KEY"]
    missing  = [k for k in required if not os.environ.get(k)]

    safe_print("=== 환경변수 검증 ===")
    for k in required + optional:
        val = os.environ.get(k, "")
        status = "OK" if val else ("필수-누락" if k in required else "미설정")
        display = f"{val[:8]}..." if val else "(없음)"
        safe_print(f"  {k:<30} {display:<15} [{status}]")
    safe_print()
    return missing


def restore_youtube_token() -> bool:
    import config as cfg

    raw = os.environ.get("YOUTUBE_TOKEN_ODANGYEOK", "")
    if raw:
        try:
            json.loads(raw)
            cfg.YT_TOKEN_FILE.write_text(raw, encoding="utf-8")
            safe_print("  [AUTH] YOUTUBE_TOKEN_ODANGYEOK 에서 토큰 복원")
            return True
        except Exception as e:
            safe_print(f"  [AUTH] raw JSON 파싱 실패: {e}")

    b64 = os.environ.get("YOUTUBE_TOKEN_ODANGYEOK_B64", "")
    if b64:
        try:
            cfg.YT_TOKEN_FILE.write_text(
                base64.b64decode(b64).decode("utf-8"), encoding="utf-8"
            )
            safe_print("  [AUTH] YOUTUBE_TOKEN_ODANGYEOK_B64 에서 토큰 복원")
            return True
        except Exception as e:
            safe_print(f"  [AUTH] B64 파싱 실패: {e}")

    if cfg.YT_TOKEN_FILE.exists():
        safe_print("  [AUTH] 기존 토큰 파일 사용")
        return True

    safe_print("  [AUTH] YouTube 토큰 없음 — 큐에만 저장")
    return False


def parse_args() -> dict:
    args = sys.argv[1:]
    result = {"era": None, "difficulty": None, "type": None, "upload": True, "count": 1}
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--era" and i + 1 < len(args):
            result["era"] = args[i+1]; i += 2
        elif a == "--difficulty" and i + 1 < len(args):
            result["difficulty"] = args[i+1]; i += 2
        elif a == "--type" and i + 1 < len(args):
            result["type"] = args[i+1]; i += 2
        elif a == "--count" and i + 1 < len(args):
            result["count"] = int(args[i+1]); i += 2
        elif a == "--no-upload":
            result["upload"] = False; i += 1
        else:
            i += 1
    return result


def main() -> int:
    safe_print("=" * 60)
    safe_print("  오당역 — CI Run")
    safe_print("=" * 60)

    missing = validate_env()
    if missing:
        safe_print(f"[FATAL] 필수 환경변수 누락: {missing}")
        return 1

    safe_print("=== 토큰 복원 ===")
    has_token = restore_youtube_token()
    safe_print()

    args = parse_args()
    safe_print("=== 파라미터 ===")
    safe_print(f"  era:        {args['era'] or 'auto'}")
    safe_print(f"  difficulty: {args['difficulty'] or 'auto'}")
    safe_print(f"  type:       {args['type'] or 'auto'}")
    safe_print(f"  count:      {args['count']}")
    safe_print(f"  upload:     {args['upload']}")
    safe_print()

    sys.path.insert(0, str(REPO_ROOT))
    import quiz_factory

    succeeded, failed = 0, 0
    for i in range(args["count"]):
        try:
            job = quiz_factory.run_pipeline(
                era_override=args["era"],
                difficulty_override=args["difficulty"],
                type_override=args["type"],
                upload=args["upload"] and has_token,
                slot_index=i % 3,
            )
            if job["status"] == "completed":
                succeeded += 1
                safe_print(f"  [OK] {job.get('title', '')}")
                safe_print(f"  영상: {job.get('video_path', 'N/A')}")
            else:
                failed += 1
                safe_print(f"  [FAIL] {job.get('error', 'Unknown')}")
        except Exception as e:
            failed += 1
            safe_print(f"  [FAIL] Crash: {e}")
            try:
                traceback.print_exc()
            except ValueError:
                pass

    safe_print(f"\n결과: {succeeded}성공 / {failed}실패")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
