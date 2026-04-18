# 오당역 (odangyeok-auto)

**오! 당신은 역사퀴즈왕** — 하루 한 문제씩 올라오는 2분 한국사·세계사 퀴즈 영상을 자동 생성·업로드하는 파이프라인.

## 영상 포맷 (150초 · 5문제 챌린지 + CTA)

매 에피소드 = **5문제 × 24초 + CTA 아웃트로 30초 = 150초**. 한 문제 24초 구성:

| 구간 | 길이 | 내용 |
| --- | ---:| --- |
| 퀴즈 제시 | 5s | OX 또는 4지선다 문제 — nova(여) 나레이션 + 큰 자막 (보기는 자막 전용) |
| 카운트다운 | 3s | 3→2→1 (비프음 3회, 마지막 길고 낮게 강조 · 매 초 밝기 펄스) |
| 정답 공개 | 3s | 화면 플래시 + "정답: O / X / N번" 크게 + **onyx(남) 음성만** |
| 해설 | 13s | shimmer(여) — 근거·맥락 간결하게 ("정답은 ..." 금지, 중복 방지) |

**CTA 아웃트로 (30s, 120~150s)** — onyx(남) 낭독 + 빨간 구독 박스 오버레이:
- 점수 댓글 요청 → 구독·알림 요청 → 다음 편 티저
- 화면: `역사퀴즈왕 도전!` 큰 훅 + 중앙 펄스 배지 (구독 / 댓글 / 다음 편)

각 문제 사이: 0.35s 화이트 플래시. 문제 번호 배지(`문제 1/5` 등)는 상단 좌측 고정.

## 구성

- **퀴즈 유형**: `OX` / `4지선다` 를 히스토리 기준 번갈아
- **난이도 가중**: 초급 60% · 중급 30% · 고급 10%
- **시대 로테이션**: 삼국 / 고려 / 조선 / 근현대 / 세계사 (각 20%, 결손 기반 결정)
- **팩트체크**: GPT-4o-mini 2-pass (생성 프롬프트 + 별도 검증 콜)
- **중복 방지**: `quiz_history.json` 최근 80개 질문·제목 금지 목록 주입

## 기술 스택

- 퀴즈·해설 생성: OpenAI GPT-4o-mini
- 음성: OpenAI TTS (`nova` / `onyx` / `shimmer` 를 구간별로)
- 이미지: DALL-E 3 1차, Replicate Flux-schnell 폴백
- 렌더링: FFmpeg (libass / drawtext)
- 업로드: YouTube Data API v3 + OAuth2
- CI: GitHub Actions (cron 3회/일, concurrency lock)

## 실행

```bash
# 로컬
python quiz_factory.py                     # 자동 (시대·난이도·유형 자동)
python quiz_factory.py --era 조선          # 시대 지정
python quiz_factory.py --difficulty 초급   # 난이도 지정
python quiz_factory.py --type OX           # 유형 지정
python quiz_factory.py --no-upload         # 업로드 스킵 (영상만)
python quiz_factory.py --count 3           # 3개 연속 생성
```

## 환경 변수 (GitHub Secrets)

| Secret | 용도 | 필수 |
| --- | --- | :---:|
| `OPENAI_API_KEY` | GPT-4o-mini / TTS / DALL-E | ✅ |
| `REPLICATE_API_TOKEN` | DALL-E 실패 시 Flux-schnell 폴백 | |
| `PIXABAY_API_KEY` | BGM 다운로드 시도 (현재는 CC BY fallback URL 사용) | |
| `YOUTUBE_API_KEY` | YouTube Data API (통계용) | |
| `YOUTUBE_TOKEN_ODANGYEOK` | OAuth2 토큰 JSON (업로드용) | ✅ (업로드 시) |
| `GITHUB_TOKEN` | 히스토리 자동 커밋 | 자동 제공 |

`system/.env.example` 복사 → `system/.env` 에 로컬 값 채워넣기 (git-ignored).

## YouTube 토큰 준비

로컬에서 최초 1회 OAuth 인증 → `youtube_token_odangyeok.json` 생성 후,
파일 내용을 GitHub Secret `YOUTUBE_TOKEN_ODANGYEOK` 에 그대로 붙여넣기.

## 디렉토리 구조

```
odangyeok-auto/
├── quiz_factory.py              # 오케스트레이터
├── factory/
│   ├── config.py                # 상수·시대·난이도 가중치
│   ├── quiz_gen.py              # GPT 퀴즈 생성 + 팩트체크
│   ├── tts.py                   # 4-segment TTS 합성
│   ├── image_gen.py             # DALL-E / Replicate
│   ├── background.py            # 시대별 배경 선택
│   ├── subtitles.py             # ASS 4구간 오버레이
│   ├── renderer.py              # FFmpeg 60초 합성
│   ├── thumbnail.py             # 1280x720 썸네일
│   ├── uploader.py              # YouTube OAuth2
│   └── run_ci.py                # GitHub Actions 진입점
├── .github/workflows/odangyeok.yml
├── system/.env.example
├── assets/
├── quiz_history.json            # 중복 방지
├── requirements.txt
└── README.md
```

## 업로드 스케줄

`cfg.UPLOAD_SLOTS = ["00:00", "12:00", "18:00"]` (UTC 기준)
→ KST 09:00 / 21:00 / 03:00 로 예약 업로드 (publishAt).
