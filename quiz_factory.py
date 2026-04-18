"""
오당역 — 메인 오케스트레이터 (episode = 5 quizzes × 24s = 120s)

파이프라인:
  1) 퀴즈 5개 배치 생성 (시대 다양화 · 유형 번갈아)
  2) TTS 에피소드 합성 (5 × 24s = 120s · 비프 카운트다운 포함)
  3) 배경 이미지 (첫 퀴즈 시대 기반)
  4) 자막 (5문제 오버레이 · 문제 번호 배지)
  5) 썸네일 (5문제 챌린지 훅)
  6) 영상 렌더링 (FFmpeg + BGM -20dB)
  7) YouTube 업로드 (OAuth2 예약)

사용:
  python quiz_factory.py                # 자동
  python quiz_factory.py --era 조선     # 5문제 모두 조선으로 강제
  python quiz_factory.py --no-upload    # 업로드 스킵
  python quiz_factory.py --count 1      # 에피소드 1개 (count>1이면 여러 에피소드)
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


def _build_episode_meta(quizzes: list[dict]) -> dict:
    """에피소드(5문제) 레벨의 제목·썸네일 텍스트·태그 생성."""
    eras = list(dict.fromkeys([q.get("era", "") for q in quizzes]))
    diffs = list(dict.fromkeys([q.get("difficulty", "") for q in quizzes]))

    ep_num = quizzes[0].get("episode_num", "")
    title_prefix = f"[오당역 {ep_num}회]" if ep_num else "[오당역]"
    era_hint     = " · ".join(eras[:3]) if eras else "한국사"
    title = f"{title_prefix} 역사퀴즈 5문제 챌린지 🧠 ({era_hint})"

    thumbnail_text = "5문제 다 맞히면 역사퀴즈왕!"

    tags = ["역사퀴즈", "퀴즈챌린지", cfg.CHANNEL_NAME, "한국사퀴즈", "역사쇼츠"]
    for e in eras:
        if e:
            tags.append(e)
    for d in diffs:
        if d:
            tags.append(d)

    return {
        "episode_num":    ep_num,
        "title":          title[:95],
        "thumbnail_text": thumbnail_text,
        "tags":           list(dict.fromkeys(tags))[:30],
        "eras":           eras,
        "difficulties":   diffs,
    }


def run_pipeline(
    era_override: str | None = None,
    difficulty_override: str | None = None,
    type_override: str | None = None,
    upload: bool = True,
    slot_index: int = 0,
) -> dict:
    ts      = datetime.now().strftime("%Y%m%d_%H%M%S")
    job_id  = f"odangyeok_{ts}"
    job     = {"job_id": job_id, "status": "started", "error": None}
    job_dir = cfg.WORKSPACE / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    log.info(f"=== 시작: {job_id} ===")

    try:
        # ── 1. 퀴즈 5개 배치 생성 ────────────────────────────────────────────
        log.info(f"[1/7] 퀴즈 {cfg.NUM_QUIZZES}문제 배치 생성...")
        from quiz_gen import generate_quiz_batch
        quizzes = generate_quiz_batch(
            n=cfg.NUM_QUIZZES,
            era_override=era_override,
            difficulty_override=difficulty_override,
            type_override=type_override,
        )
        episode_meta = _build_episode_meta(quizzes)
        job.update({
            "episode_num":  episode_meta["episode_num"],
            "title":        episode_meta["title"],
            "eras":         episode_meta["eras"],
            "difficulties": episode_meta["difficulties"],
            "quizzes":      [{
                "era": q["era"],
                "difficulty": q["difficulty"],
                "type": q["type"],
                "question": q["question"],
                "answer": q["answer"],
            } for q in quizzes],
        })
        for i, q in enumerate(quizzes):
            log.info(f"  Q{i+1}/{cfg.NUM_QUIZZES} [{q['era']}/{q['difficulty']}/{q['type']}] {q['question']} → {q['answer']}")

        # ── 2. TTS 에피소드 합성 ────────────────────────────────────────────
        log.info("[2/7] TTS 에피소드 합성...")
        from tts import generate_episode_tts
        audio_path = job_dir / "audio.mp3"
        audio_path, segments = generate_episode_tts(quizzes, audio_path, job_dir)

        # ── 3. 배경 이미지 ──────────────────────────────────────────────────
        # 5문제 섞여 있으므로 퀴즈쇼 느낌 중립 배경 — 첫 문제 시대로만 힌트
        log.info("[3/7] 배경 이미지 생성...")
        from background import get_background
        bg_path = get_background(quizzes[0]["era"], job_dir)
        log.info(f"  배경: {bg_path.name}")

        # ── 4. 자막 ──────────────────────────────────────────────────────────
        log.info("[4/7] 자막 생성...")
        from subtitles import generate_episode_subtitles
        subs_path = job_dir / "subs.ass"
        subs_path = generate_episode_subtitles(quizzes, subs_path)

        # ── 5. 썸네일 ────────────────────────────────────────────────────────
        log.info("[5/7] 썸네일 생성...")
        from thumbnail import generate_episode_thumbnail
        thumb_path = job_dir / "thumbnail.jpg"
        thumb_path = generate_episode_thumbnail(quizzes, episode_meta, thumb_path, job_dir, bg_path)

        # ── 6. 영상 렌더링 ───────────────────────────────────────────────────
        log.info("[6/7] 영상 렌더링...")
        from renderer import render_video
        video_filename = f"{job_id}_ep{episode_meta['episode_num']}.mp4"
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
        from uploader import build_episode_metadata
        publish_at = _next_publish_time(slot_index)
        meta = build_episode_metadata(quizzes, episode_meta, publish_at=publish_at)

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
    safe_print(f"  {cfg.NUM_QUIZZES}문제 × {int(cfg.QUIZ_DURATION)}s = {int(cfg.TOTAL_DURATION)}s")
    safe_print(f"  Python {sys.version.split()[0]}")
    safe_print("=" * 60)

    if not cfg.OPENAI_API_KEY:
        safe_print("[오류] OPENAI_API_KEY 가 설정되지 않았습니다.")
        sys.exit(1)

    args  = parse_args()
    count = max(1, args["count"])
    succeeded, failed = 0, 0

    for i in range(count):
        if count > 1:
            safe_print(f"\n{'=' * 60}\n  에피소드 {i+1}/{count}\n{'=' * 60}")
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
