"""
odangyeok-auto — GitHub Secrets 등록 헬퍼

사용법:
    # 1회 설치
    pip install pynacl requests

    # 개별 Secret 설정 (값을 환경변수로 주입 — shell history에 남지 않게)
    export SECRET_VALUE='sk-...'
    python scripts/set_secret.py OPENAI_API_KEY

    # 또는 파일에서 읽기 (YouTube OAuth JSON 같은 다줄 값에 유용)
    python scripts/set_secret.py YOUTUBE_TOKEN_ODANGYEOK --file youtube_token_odangyeok.json

GitHub PAT 토큰은 `GITHUB_TOKEN` 환경변수 또는 villain-auto remote 에서 자동 추출.
"""

import argparse
import os
import subprocess
import sys
from base64 import b64encode
from pathlib import Path

import requests
from nacl import encoding, public

REPO = "jleemedia01/odangyeok-auto"


def _get_github_token() -> str:
    """GITHUB_TOKEN 환경변수 우선, 없으면 villain-auto remote URL 에서 추출."""
    tok = os.environ.get("GITHUB_TOKEN")
    if tok:
        return tok
    villain_path = Path.home() / "villain-auto"
    if villain_path.exists():
        try:
            url = subprocess.check_output(
                ["git", "-C", str(villain_path), "remote", "get-url", "origin"],
                text=True,
            ).strip()
            # https://<TOKEN>@github.com/...
            if "@" in url and "https://" in url:
                return url.split("https://")[1].split("@")[0]
        except Exception:
            pass
    sys.exit(
        "[오류] GitHub PAT 토큰이 필요합니다.\n"
        "  export GITHUB_TOKEN='ghp_...' 로 주입하세요."
    )


def _get_public_key(token: str) -> dict:
    r = requests.get(
        f"https://api.github.com/repos/{REPO}/actions/secrets/public-key",
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
        },
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def _encrypt(public_key_b64: str, secret_value: str) -> str:
    """GitHub API spec: libsodium sealed box, then base64."""
    pk = public.PublicKey(public_key_b64.encode("utf-8"), encoding.Base64Encoder())
    sealed = public.SealedBox(pk)
    encrypted = sealed.encrypt(secret_value.encode("utf-8"))
    return b64encode(encrypted).decode("utf-8")


def set_secret(name: str, value: str) -> None:
    token = _get_github_token()
    key_data = _get_public_key(token)
    encrypted = _encrypt(key_data["key"], value)

    r = requests.put(
        f"https://api.github.com/repos/{REPO}/actions/secrets/{name}",
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
        },
        json={"encrypted_value": encrypted, "key_id": key_data["key_id"]},
        timeout=15,
    )
    if r.status_code in (201, 204):
        print(f"✅ {name} → {REPO} 등록 완료 (HTTP {r.status_code})")
    else:
        sys.exit(f"[오류] 등록 실패: HTTP {r.status_code}\n{r.text}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("name", help="Secret 이름 (예: OPENAI_API_KEY)")
    ap.add_argument("--file", help="값을 읽을 파일 경로 (다줄 값에 사용)")
    ap.add_argument(
        "--env", default="SECRET_VALUE",
        help="값을 읽을 환경변수 이름 (기본: SECRET_VALUE)",
    )
    args = ap.parse_args()

    if args.file:
        value = Path(args.file).read_text(encoding="utf-8").strip()
        source = f"file={args.file}"
    else:
        value = os.environ.get(args.env, "")
        source = f"env={args.env}"
        if not value:
            sys.exit(
                f"[오류] ${args.env} 가 비어있습니다.\n"
                f"  export {args.env}='<값>' 로 먼저 주입하세요."
            )

    print(f"등록 준비: {args.name} ← {source} ({len(value)}자)")
    set_secret(args.name, value)


if __name__ == "__main__":
    main()
