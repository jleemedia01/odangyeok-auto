"""
오당역 — YouTube Uploader
OAuth2 인증 후 YouTube에 영상 + 썸네일 업로드. 토큰 없으면 큐 파일에 저장.
"""

import base64
import json
import os
import time
from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

from config import YT_TOKEN_FILE, YT_SCOPES, YT_CATEGORY_ID, CHANNEL_NAME, CHANNEL_TAGLINE

CHUNK_SIZE = 1024 * 1024 * 8
FIRST_COMMENT = "정답 맞추셨나요? 댓글로 알려주세요 👇 매일 새 문제 올라옵니다!"


def _creds_from_data(data: dict) -> Credentials:
    return Credentials(
        token=data.get("token"),
        refresh_token=data.get("refresh_token"),
        token_uri=data.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=data.get("client_id"),
        client_secret=data.get("client_secret"),
        scopes=data.get("scopes", YT_SCOPES),
    )


def _load_credentials() -> Credentials | None:
    # 1. YOUTUBE_TOKEN_ODANGYEOK (raw JSON env var)
    raw = os.environ.get("YOUTUBE_TOKEN_ODANGYEOK", "")
    if raw:
        try:
            print("  [업로드] YOUTUBE_TOKEN_ODANGYEOK 에서 토큰 로드")
            return _creds_from_data(json.loads(raw))
        except Exception as e:
            print(f"  [업로드] YOUTUBE_TOKEN_ODANGYEOK 파싱 실패: {e}")

    # 2. base64 form
    b64 = os.environ.get("YOUTUBE_TOKEN_ODANGYEOK_B64", "")
    if b64:
        try:
            data = json.loads(base64.b64decode(b64).decode("utf-8"))
            print("  [업로드] YOUTUBE_TOKEN_ODANGYEOK_B64 에서 토큰 로드")
            return _creds_from_data(data)
        except Exception as e:
            print(f"  [업로드] B64 파싱 실패: {e}")

    # 3. 로컬 파일
    if YT_TOKEN_FILE.exists():
        try:
            print("  [업로드] 로컬 토큰 파일 사용")
            return Credentials.from_authorized_user_file(str(YT_TOKEN_FILE), YT_SCOPES)
        except Exception as e:
            print(f"  [업로드] 로컬 토큰 로드 실패: {e}")

    return None


def get_youtube_service():
    creds = _load_credentials()
    if not creds:
        raise FileNotFoundError(
            "YouTube 토큰 없음. CI: YOUTUBE_TOKEN_ODANGYEOK Secret 등록 필요."
        )
    if not creds.valid and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        print("  [업로드] 토큰 갱신 완료")
        if YT_TOKEN_FILE.parent.exists():
            YT_TOKEN_FILE.write_text(creds.to_json())
    return build("youtube", "v3", credentials=creds)


def build_metadata(quiz: dict, publish_at: str | None = None) -> dict:
    title   = quiz.get("title", "역사 퀴즈")
    era     = quiz.get("era", "")
    diff    = quiz.get("difficulty", "")
    qtype   = quiz.get("type", "")

    description = (
        f"{title}\n\n"
        f"#역사퀴즈 #{era} #{CHANNEL_NAME} #한국사 #{qtype}\n\n"
        f"📌 {CHANNEL_TAGLINE}\n"
        f"하루 한 문제, 역사 지식 쑥쑥! 맞추면 당신도 역사퀴즈왕!\n\n"
        f"🎯 난이도: {diff}   |   시대: {era}   |   유형: {qtype}\n\n"
        f"🔔 구독 + 알림 설정하고 매일 새 문제 풀어보세요.\n"
        f"👇 정답 & 해설은 영상 안에서 공개됩니다!\n\n"
        f"⚠️ 모든 문제는 역사 사실에 기반한 교육 목적의 콘텐츠입니다."
    )

    tags = (quiz.get("tags", []) or []) + [
        "역사퀴즈", "한국사퀴즈", CHANNEL_NAME, "쇼츠", "역사쇼츠",
        era, diff, qtype,
    ]

    meta = {
        "title":       title,
        "description": description,
        "tags":        list(dict.fromkeys([t for t in tags if t]))[:30],
        "categoryId":  YT_CATEGORY_ID,
        "privacyStatus": "private",
    }
    if publish_at:
        meta["publishAt"] = publish_at
    return meta


def upload_video(service, video_path: Path, thumbnail_path: Path | None, metadata: dict) -> str | None:
    snippet = {
        "title":       metadata["title"],
        "description": metadata["description"],
        "tags":        metadata.get("tags", []),
        "categoryId":  metadata.get("categoryId", YT_CATEGORY_ID),
    }
    status = {"selfDeclaredMadeForKids": False}
    if metadata.get("publishAt"):
        status["privacyStatus"] = "private"
        status["publishAt"]     = metadata["publishAt"]
    else:
        status["privacyStatus"] = metadata.get("privacyStatus", "private")

    body  = {"snippet": snippet, "status": status}
    media = MediaFileUpload(str(video_path), mimetype="video/mp4", chunksize=CHUNK_SIZE, resumable=True)

    print(f"  [업로드] 업로드 중: {metadata['title']}")
    for attempt in range(1, 4):
        try:
            req = service.videos().insert(part="snippet,status", body=body, media_body=media)
            response = None
            while response is None:
                s, response = req.next_chunk()
                if s:
                    print(f"  [업로드] {int(s.progress() * 100)}%...", end="\r")

            vid = response.get("id")
            print(f"\n  [업로드] 완료! ID: {vid} | https://youtu.be/{vid}")

            if thumbnail_path and thumbnail_path.exists() and vid:
                try:
                    service.thumbnails().set(
                        videoId=vid,
                        media_body=MediaFileUpload(str(thumbnail_path)),
                    ).execute()
                    print("  [업로드] 썸네일 업로드 완료")
                except Exception as e:
                    print(f"  [업로드] 썸네일 실패 (무시): {e}")

            if vid:
                try:
                    service.commentThreads().insert(
                        part="snippet",
                        body={"snippet": {"videoId": vid, "topLevelComment": {"snippet": {"textOriginal": FIRST_COMMENT}}}},
                    ).execute()
                except Exception:
                    pass

            return vid

        except HttpError as e:
            if e.resp.status in (500, 502, 503, 504) and attempt < 3:
                wait = 2 ** attempt
                print(f"  [업로드] 서버오류 {e.resp.status}, {wait}초 재시도...")
                time.sleep(wait)
            else:
                print(f"  [업로드] 실패: {e}")
                return None
    return None


def save_to_queue(video_path: Path, thumbnail_path: Path | None, metadata: dict, queue_file: Path) -> None:
    queue = []
    if queue_file.exists():
        try:
            queue = json.loads(queue_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    queue.append({
        "video_path":     str(video_path),
        "thumbnail_path": str(thumbnail_path) if thumbnail_path else None,
        "title":          metadata.get("title", ""),
        "publish_at":     metadata.get("publishAt"),
        "privacy":        metadata.get("privacyStatus", "private"),
    })
    queue_file.write_text(json.dumps(queue, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  [업로드] 큐 저장: {queue_file.name} (총 {len(queue)}개)")
