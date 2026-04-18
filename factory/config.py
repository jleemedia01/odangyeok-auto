"""
오당역 — Configuration
채널: 오당역 (오! 당신은 역사퀴즈왕)
컨텐츠: 60초 역사 퀴즈 쇼츠 (OX / 4지선다)
"""

import os
from pathlib import Path

# ── Path resolution ────────────────────────────────────────────────────────────
FACTORY_DIR   = Path(__file__).parent
REPO_ROOT     = FACTORY_DIR.parent
ASSETS_DIR    = REPO_ROOT / "assets"
WORKSPACE     = REPO_ROOT / "workspace"
OUTPUT_VIDEOS = REPO_ROOT / "output" / "videos"

for d in [WORKSPACE, OUTPUT_VIDEOS, ASSETS_DIR / "backgrounds", ASSETS_DIR / "music"]:
    d.mkdir(parents=True, exist_ok=True)

# ── Secrets ────────────────────────────────────────────────────────────────────
_env_path = REPO_ROOT / "system" / ".env"
if _env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(_env_path)

OPENAI_API_KEY     = os.environ.get("OPENAI_API_KEY", "")
REPLICATE_API_TOKEN = os.environ.get("REPLICATE_API_TOKEN", "")
YOUTUBE_API_KEY    = os.environ.get("YOUTUBE_API_KEY", "")

# ── Channel info ───────────────────────────────────────────────────────────────
CHANNEL_NAME    = "오당역"
CHANNEL_TAGLINE = "오! 당신은 역사퀴즈왕"
CHANNEL_SUBTITLE = "하루 한 문제, 역사 퀴즈왕 도전!"

# ── Episode = 5 quizzes × 24s + CTA 12s = 132s (2분 12초) ─────────────────────
NUM_QUIZZES     = 5
SEG_QUESTION    = 5.0    # 문제 제시
SEG_COUNTDOWN   = 3.0    # 3→2→1 (비프음)
SEG_REVEAL      = 3.0    # 정답 공개
SEG_EXPLANATION = 13.0   # 해설
QUIZ_DURATION   = SEG_QUESTION + SEG_COUNTDOWN + SEG_REVEAL + SEG_EXPLANATION   # 24.0
SEG_CTA         = 12.0   # 짧은 CTA: 좋아요·구독·알림 3개 배지 각 4s
TOTAL_DURATION  = NUM_QUIZZES * QUIZ_DURATION + SEG_CTA                          # 132.0
CTA_START       = NUM_QUIZZES * QUIZ_DURATION                                    # 120.0

# ── CTA 고정 멘트 (12초 안에 읽힘, 남성 onyx 낭독) ─────────────────────────────
CTA_FIXED_TEXT = "좋아요, 구독, 알림 설정 부탁드립니다!"

# ── 채널 헤더 (상단 고정 오버레이, 전체 132초 동안 노출) ──────────────────────
CHANNEL_HEADER_TEXT = "오! 당신은 역사퀴즈왕"
CHANNEL_HEADER_FONTSIZE = 90
CHANNEL_HEADER_Y        = 50

# ── Transition between quizzes (부드러운 페이드 전환) ─────────────────────────
# 총 1.0초 구성: fade-in 0.4s → hold 0.2s → fade-out 0.4s, 중심이 문제 경계
QUIZ_TRANSITION_FADE_IN   = 0.4
QUIZ_TRANSITION_HOLD      = 0.2
QUIZ_TRANSITION_FADE_OUT  = 0.4
QUIZ_TRANSITION_PEAK      = 0.50   # brightness 피크 (0.0~1.0)
QUIZ_TRANSITION_TOTAL     = QUIZ_TRANSITION_FADE_IN + QUIZ_TRANSITION_HOLD + QUIZ_TRANSITION_FADE_OUT  # 1.0s
QUIZ_TRANSITION_FADE      = QUIZ_TRANSITION_TOTAL   # 하위 호환 별칭

# ── LLM ────────────────────────────────────────────────────────────────────────
LLM_MODEL = "gpt-4o-mini"

# ── TTS ────────────────────────────────────────────────────────────────────────
TTS_MODEL         = "tts-1-hd"  # HD 모델 — 한국어 발음 더 정확 (cost 2x)
TTS_VOICE_QUESTION = "nova"     # 또렷한 여성 — 문제 제시
TTS_VOICE_REVEAL   = "onyx"     # 무게감 있는 남성 — 정답 공개
TTS_VOICE_EXPLAIN  = "shimmer"  # 친근한 여성 — 해설
TTS_VOICE_CTA      = "onyx"     # 무게감 있는 남성 — 아웃트로 CTA
TTS_SPEED_QUESTION = 1.05       # 질문은 정확한 발음 우선 — 과속 지양
TTS_SPEED_EXPLAIN  = 1.10       # 13초 안에 확실히 읽히게
TTS_SPEED_CTA      = 1.0

# ── Video specs ────────────────────────────────────────────────────────────────
VIDEO_WIDTH   = 1080
VIDEO_HEIGHT  = 1920
VIDEO_FPS     = 30
VIDEO_CODEC   = "libx264"
VIDEO_PRESET  = "ultrafast"
VIDEO_CRF     = 30
AUDIO_CODEC   = "aac"
AUDIO_BITRATE = "320k"
BGM_VOLUME    = 0.10     # ≈ -20dB — TTS 간섭 방지
TTS_VOLUME    = 1.0

# ── Subtitle styling ───────────────────────────────────────────────────────────
SUBTITLE_FONT           = "NanumGothicBold"
SUBTITLE_FONT_SIZE      = 62
SUBTITLE_OUTLINE        = 8     # 얇은 외곽선 (가독성 유지하면서 깔끔하게)
SUBTITLE_SHADOW         = 0
SUBTITLE_MARGIN_V       = 600

# ── Thumbnail ──────────────────────────────────────────────────────────────────
THUMBNAIL_WIDTH   = 1280
THUMBNAIL_HEIGHT  = 720

# ── Font detection ─────────────────────────────────────────────────────────────
def _find_font(candidates):
    for p in candidates:
        if Path(p).exists():
            return p
    return None

FONT_BOLD = _find_font([
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothicExtraBold.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
])
FONT_REGULAR = _find_font([
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
])

# ── 시대 분류 (Era) ────────────────────────────────────────────────────────────
ERAS: dict[str, str] = {
    "삼국":   "고조선·삼국시대·가야·통일신라·발해 (BC 2333 ~ AD 918)",
    "고려":   "고려 (918 ~ 1392)",
    "조선":   "조선 (1392 ~ 1897)",
    "근현대": "대한제국·일제강점기·대한민국 (1897 ~ 현재)",
    "세계사": "세계사 (고대 ~ 20세기)",
}

ERA_ORDER: list[str] = ["삼국", "고려", "조선", "근현대", "세계사"]

# 목표 시대 분포 — 사용자 요청: 한국사 80%, 세계사 20% 가정
# 한국사 4시기에 균등 분배 (20%씩), 세계사 20%
ERA_WEIGHTS: dict[str, float] = {
    "삼국":   0.20,
    "고려":   0.20,
    "조선":   0.20,
    "근현대": 0.20,
    "세계사": 0.20,
}

# ── 난이도 분류 (Difficulty) ───────────────────────────────────────────────────
# 중학교 1학년 학생이 공부하면 맞힐 수 있는 수준 기준.
# 단순 암기보다 이해·맥락 중심. 너무 쉬운 상식 문제 배제.
DIFFICULTIES: dict[str, str] = {
    "초급": (
        "중학교 1학년 교과서 기본 수준 — 연도·인물·사건의 1:1 매칭. "
        "예: 세종대왕 즉위년(1418), 임진왜란 발발년도(1592)"
    ),
    "중급": (
        "중1~중2 심화 수준 — 역사 흐름·인과관계 이해 필요. "
        "예: 고려 광종의 개혁 정책, 조선 세도정치 시작 인물"
    ),
    "고급": (
        "중3~고1 수준 — 사건의 복합적 원인·사상적 배경 분석. "
        "예: 갑신정변 주도 인물들의 사상적 배경"
    ),
}

DIFFICULTY_WEIGHTS: dict[str, float] = {
    "초급": 0.30,
    "중급": 0.50,
    "고급": 0.20,
}

# ── 퀴즈 유형 (Type) ───────────────────────────────────────────────────────────
QUIZ_TYPES: list[str] = ["OX", "4지선다"]

# ── 시대별 배경 컬러 (썸네일 + 그라디언트 폴백) ────────────────────────────────
ERA_COLORS: dict[str, tuple[tuple[int, int, int], tuple[int, int, int]]] = {
    # (primary, accent)
    "삼국":   ((156,  92,  43), (234, 179, 108)),  # 흙빛·청동빛
    "고려":   (( 61,  90, 128), (168, 192, 224)),  # 청자색
    "조선":   ((124,  45,  18), (237, 180, 108)),  # 단청 주홍
    "근현대": (( 45,  55,  72), (229, 231, 235)),  # 세피아 모노크롬
    "세계사": ((120,  53, 132), (246, 214,  92)),  # 보라·금
}

# ── 이미지 생성 backend ────────────────────────────────────────────────────────
# "dalle" | "replicate" — 우선 DALL-E 3 사용, 실패 시 Replicate 폴백
IMAGE_BACKEND_PRIMARY  = "dalle"
IMAGE_BACKEND_FALLBACK = "replicate"
REPLICATE_MODEL = "black-forest-labs/flux-schnell"

# ── YouTube ────────────────────────────────────────────────────────────────────
YT_TOKEN_FILE   = REPO_ROOT / "youtube_token_odangyeok.json"
YT_SECRETS_FILE = REPO_ROOT / "client_secret.json"
YT_CATEGORY_ID  = "27"          # Education
YT_DEFAULT_PRIVACY = "private"
YT_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]

# ── Upload schedule (KST 기준 인기 시간대) ─────────────────────────────────────
# 18:00 UTC = 03:00 KST
# 00:00 UTC = 09:00 KST
# 12:00 UTC = 21:00 KST
UPLOAD_SLOTS = ["00:00", "12:00", "18:00"]

LOG_FILE = REPO_ROOT / "factory.log"
