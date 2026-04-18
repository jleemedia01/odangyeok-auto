"""
odangyeok-auto — YouTube OAuth 토큰 발급 스크립트

전제:
  1) Google Cloud Console 에서 OAuth 2.0 클라이언트 생성 → client_secret.json 다운로드
  2) 이 파일을 odangyeok-auto/client_secret.json 로 저장
  3) YouTube Data API v3 이 해당 프로젝트에 활성화돼 있어야 함
  4) 채널을 소유한 Google 계정으로 로그인

사용:
  pip install google-auth google-auth-oauthlib
  python scripts/setup_auth.py

출력:
  youtube_token_odangyeok.json  (로컬 인증용 — .gitignore 처리됨)
  + GitHub Secret YOUTUBE_TOKEN_ODANGYEOK 등록용 JSON 표준출력에 복사 가능한 형태로 인쇄
"""

import json
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]

REPO_ROOT = Path(__file__).parent.parent
CLIENT_SECRET = REPO_ROOT / "client_secret.json"
TOKEN_OUT     = REPO_ROOT / "youtube_token_odangyeok.json"


def main() -> None:
    if not CLIENT_SECRET.exists():
        print(f"[오류] {CLIENT_SECRET} 이 없습니다.")
        print("Google Cloud Console → 사용자 인증 정보 → OAuth 2.0 클라이언트 ID 생성 후")
        print("다운로드한 JSON 파일을 위 경로로 저장하세요.")
        sys.exit(1)

    print("브라우저가 열립니다.")
    print("'오당역' 채널을 소유한 Google 계정으로 로그인 후 '허용' 클릭하세요.\n")

    flow  = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
    creds = flow.run_local_server(port=0)

    token_data = {
        "token":         creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri":     creds.token_uri,
        "client_id":     creds.client_id,
        "client_secret": creds.client_secret,
        "scopes":        list(creds.scopes) if creds.scopes else SCOPES,
    }

    TOKEN_OUT.write_text(json.dumps(token_data, indent=2), encoding="utf-8")
    print(f"✅ {TOKEN_OUT} 저장 완료")

    print("\n" + "=" * 60)
    print("다음 단계 — GitHub Secret 등록:")
    print("=" * 60)
    print(f"  python scripts/set_secret.py YOUTUBE_TOKEN_ODANGYEOK --file {TOKEN_OUT}")
    print("=" * 60)


if __name__ == "__main__":
    main()
