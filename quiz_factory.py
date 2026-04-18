"""
오당역 — 메인 오케스트레이터 (quiz_factory)

60초 역사퀴즈 쇼츠 자동 생성 파이프라인:
  1) 퀴즈 생성 (GPT-4o-mini, OX/4지선다, 시대·난이도 가중)
  2) TTS 4-segment 합성 (문제 / 무음 / 정답 / 해설 = 60초)
  3) 배경 이미지 (DALL-E 3 → Replicate 폴백)
  4) 자막 (ASS, 4구간 오버레이)
  5) 썸네일 (1280x720)
  6) 영상 렌더링 (FFmpeg)
  7) YouTube 업로드 (OAuth2, publishAt 예약)

사용:
  python quiz_factory.py                       # 자동
  python quiz_factory.py --era 조선            # 시대 지정
  python quiz_factory.py --difficulty 초급     # 난이도 지정
  python quiz_factory.py --type OX             # 유형 지정
  python quiz_factory.py --no-upload           # 업로드 스킵
  python quiz_factory.py --count 3             # 여러 개
"""

import logging
import sys
import traceback
from datetime import datetime, timedelta
from pathlib import Path


def safe_print(*args, **kwargs):
    try:
        print(*args, **kwargs, flush=True)
    except (ValueError, OSError):
        pass


REPO_ROOT   = Path(__file__).parent
FACTORY_DIR = REPO_ROOT / "factory"
sys.path.insert(0, str(FACTORY_DIR))

import config as cfg

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(str(cfg.LOG_FILE), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("OdangyeokFactory")


def _next_publish_time(slot_index: int = 0) -> str:
    slots = cfg.UPLOAD_SLOTS
    if slot_index >= len(slots):
        slot_index = 0
    now = datetime.utcnow()
    hour, minute = map(int, slots[slot_index].split(":"))
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def run_pipeline(
    era_override: str | None = None,
    difficulty_override: str | None = None,
    type_override: str | None = None,
    upload: bool = True,
    slot_index: int = 0,
) -> dict:
    ts     = datetime.now().strftime("%Y%m%d_%H%M%S")
    job_id = f"odangyeok_{ts}"
    job    = {"job_id": job_id, "status": "started", "error": None}
    job_dir = cfg.WORKSPACE / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    log.info(f"=== 시작: {job_id} ===")

    try:
        # ── 1. 퀴즈 생성 ─────────────────────────────────────────────────────
        log.info("[1/7] 퀴즈 생성...")
        from quiz_gen import generate_quiz
        quiz = generate_quiz(
            era_override=era_override,
            difficulty_override=difficulty_override,
            type_override=type_override,
        )
        job.update({
            "title":      quiz["title"],
            "era":        quiz["era"],
            "difficulty": quiz["difficulty"],
            "type":       quiz["type"],
            "question":   quiz["question"],
            "answer":     quiz["answer"],
        })
        log.info(f"  [{quiz['era']} / {quiz['difficulty']} / {quiz['type']}] {quiz['title']}")

        # ── 2. TTS 4-segment ─────────────────────────────────────────────────
        log.info("[2/7] TTS 4-segment 합성...")
        from tts import generate_quiz_tts
        audio_path = job_dir / "audio.mp3"
        audio_path, segments = generate_quiz_tts(quiz, audio_path, job_dir)

        # ── 3. 배경 이미지 ───────────────────────────────────────────────────
        log.info("[3/7] 배경 이미지 생성...")
        from background import get_background
        bg_path = get_background(quiz["era"], job_dir)
        log.info(f"  배경: {bg_path.name}")

        # ── 4. 자막 ──────────────────────────────────────────────────────────
        log.info("[4/7] 자막(ASS) 생성...")
        from subtitles import generate_subtitles
        subs_path = job_dir / "subs.ass"
        subs_path = generate_subtitles(quiz, subs_path)

        # ── 5. 썸네일 ────────────────────────────────────────────────────────
        log.info("[5/7] 썸네일 생성...")
        from thumbnail import generate_thumbnail
        thumb_path = job_dir / "thumbnail.jpg"
        thumb_path = generate_thumbnail(quiz, thumb_path, job_dir, bg_path)

        # ── 6. 영상 렌더링 ───────────────────────────────────────────────────
        log.info("[6/7] 영상 렌더링...")
        from renderer import render_video
        video_filename = f"{job_id}_{quiz['era']}.mp4"
        video_path = cfg.OUTPUT_VIDEOS / video_filename
        video_path = render_video(
            audio_path=audio_path,
            bg_path=bg_path,
            subs_path=subs_path,
            output_path=video_path,
        )
        job["video_path"] = str(video_path)
        log.info(f"  영상: {video_path.name}")

        # ── 7. 업로드 ────────────────────────────────────────────────────────
        log.info("[7/7] YouTube 업로드...")
        from uploader import build_metadata
        publish_at = _next_publish_time(slot_index)
        meta = build_metadata(quiz, publish_at=publish_at)

        if upload:
            try:
                from uploader import get_youtube_service, upload_video
                yt = get_youtube_service()
                vid = upload_video(yt, video_path, thumb_path, meta)
                if vid:
                    job["video_id"] = vid
                    log.info(f"  업로드 완료: https://youtu.be/{vid}")
            except FileNotFoundError as e:
                log.warning(f"  YouTube 미설정 — 큐 저장: {e}")
                _save_to_queue(video_path, thumb_path, meta)
        else:
            log.info("  업로드 스킵 (--no-upload)")

        job["status"] = "completed"
        log.info(f"=== 완료: {job_id} ===")
        return job

    except Exception as e:
        job["status"] = "failed"
        job["error"]  = str(e)
        log.error(f"=== 실패: {job_id}: {e} ===")
        log.error(traceback.format_exc())
        return job


def _save_to_queue(video_path: Path, thumb_path: Path, meta: dict) -> None:
    from uploader import save_to_queue
    save_to_queue(video_path, thumb_path, meta, cfg.REPO_ROOT / "upload_queue.json")


def parse_args() -> dict:
    args = sys.argv[1:]
    result = {"era": None, "difficulty": None, "type": None, "upload": True, "count": 1}
    i = 0
    while i < len(args):
        a = args[i]
        if   a == "--era"        and i + 1 < len(args): result["era"]        = args[i+1]; i += 2
        elif a == "--difficulty" and i + 1 < len(args): result["difficulty"] = args[i+1]; i += 2
        elif a == "--type"       and i + 1 < len(args): result["type"]       = args[i+1]; i += 2
        elif a == "--count"      and i + 1 < len(args): result["count"]      = int(args[i+1]); i += 2
        elif a == "--no-upload": result["upload"] = False; i += 1
        else: i += 1
    return result


def main():
    safe_print("=" * 60)
    safe_print(f"  {cfg.CHANNEL_NAME} — {cfg.CHANNEL_TAGLINE}")
    safe_print(f"  Python {sys.version.split()[0]}")
    safe_print("=" * 60)

    if not cfg.OPENAI_API_KEY:
        safe_print("[오류] OPENAI_API_KEY 가 설정되지 않았습니다.")
        sys.exit(1)

    args = parse_args()
    count = max(1, args["count"])
    succeeded, failed = 0, 0

    for i in range(count):
        if count > 1:
            safe_print(f"\n{'=' * 60}\n  영상 {i+1}/{count}\n{'=' * 60}")
        job = run_pipeline(
            era_override=args["era"],
            difficulty_override=args["difficulty"],
            type_override=args["type"],
            upload=args["upload"],
            slot_index=i % len(cfg.UPLOAD_SLOTS),
        )
        if job["status"] == "completed":
            succeeded += 1
            safe_print(f"\n[완료] {job.get('title', '')}")
            safe_print(f"  영상: {job.get('video_path', 'N/A')}")
            if job.get("video_id"):
                safe_print(f"  URL: https://youtu.be/{job['video_id']}")
        else:
            failed += 1
            safe_print(f"\n[실패] {job.get('error', 'Unknown error')}")

    safe_print(f"\n{'=' * 60}")
    safe_print(f"  결과: {succeeded}개 성공, {failed}개 실패")
    safe_print(f"{'=' * 60}")

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
