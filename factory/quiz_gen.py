"""
오당역 — Quiz Generator
GPT-4o-mini로 OX / 4지선다 역사 퀴즈 생성 (단일 · 배치 5문제)
- 시대 로테이션: 삼국 / 고려 / 조선 / 근현대 / 세계사
- 난이도: 초급 60% / 중급 30% / 고급 10%
- 유형: OX / 4지선다 번갈아
- 중복 방지: quiz_history.json + 유튜브 제목 금지 + 배치 내부 중복 차단
- 팩트체크 2-pass (질문/보기/정답만, 해설은 보존)
"""

import json
import random
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from openai import OpenAI

from config import (
    OPENAI_API_KEY,
    CHANNEL_NAME,
    CHANNEL_TAGLINE,
    WORKSPACE,
    REPO_ROOT,
    LLM_MODEL,
    ERAS,
    ERA_ORDER,
    ERA_WEIGHTS,
    DIFFICULTIES,
    DIFFICULTY_WEIGHTS,
    QUIZ_TYPES,
    NUM_QUIZZES,
)

HISTORY_FILE = REPO_ROOT / "quiz_history.json"

# 13s TTS 낭독 — 간결화 (공백 포함 50~100자)
EXPLANATION_MIN = 50
EXPLANATION_MAX = 100

# 질문 길이 하드 리밋 — 5s 안에 읽혀야 함 (TTS speed 1.1 기준)
QUESTION_MAX_OX  = 22
QUESTION_MAX_MC  = 24

# CTA 아웃트로 — 30s TTS (speed 1.0)
CTA_MIN = 130
CTA_MAX = 180

# 품질 임계 — confidence 95 미만은 자동 폐기
CONFIDENCE_MIN = 95

# ── 강한 시스템 프롬프트 (팩트체크 + 품질 게이트) ────────────────────────────
QUIZ_SYSTEM_PROMPT = """당신은 역사 퀴즈 출제자입니다. 정확성과 교육적 가치가 생명입니다.

【타겟 수준】
중학교 1학년 학생이 공부하면 맞힐 수 있는 수준.
공부 안 하면 틀리지만, 공부하면 맞힐 수 있는 지점.
단순 암기 아닌 이해·맥락·인과관계를 묻는 문제.

【절대 금지 문제 유형 — 생성 시 반드시 제외】
1. 동어반복 (정의상 참인 것):
   ❌ "고려의 국호는 고려이다" (국호가 곧 이름)
   ❌ "법흥왕은 신라의 왕이다" (법흥왕은 신라 역사상 정의된 왕명)
   ❌ "세종대왕의 시호는 세종이다"
   → 답이 "질문에 이미 들어있는 단어" 이면 출제 금지.

2. 공부 안 해도 아는 상식:
   ❌ "한국전쟁은 1950년에 발발했다" (너무 유명)
   ❌ "임진왜란은 1592년이다" (초등학교 수준)
   ❌ "세종대왕은 한글을 만들었다" (국민 상식)
   ❌ "서울은 대한민국의 수도다"
   → 역사 공부 안 한 사람도 80% 이상 맞힐 문제 금지.

3. 표면적 trivia:
   ❌ "콜럼버스가 탄 배의 이름은?" (본질 없는 잡지식)
   ❌ "세종대왕의 키는 몇이었나?"

【반드시 이 중 하나에 해당해야 출제 가능】
1. 인물-업적/정책 매칭: 헷갈리기 쉬운 인물의 구체 업적
   예: "노비안검법을 시행한 고려 왕은?" (광종)
2. 사건의 원인/결과/맥락: 단순 발생이 아닌 '왜' 또는 '그래서'
   예: "묘청이 서경천도를 주장한 목적은?" (금 정벌·풍수지리)
3. 유사 사건·인물 구분: 혼동하기 쉬운 두 가지 중 하나 지목
   예: "갑신정변과 갑오개혁 중 김옥균이 주도한 것은?" (갑신정변)
4. 잘 알려지지 않은 중요 사실: 교과서 있지만 흔히 잊는 내용
   예: "대조영이 건국한 나라는?" (발해)
5. 정책·제도의 구체 내용: 이름뿐 아닌 실제 작동 방식
   예: "조선 과전법에서 과전의 대상 지역은?" (경기도)

【난이도 기준】
- 초급 (30%): 중1 교과서 기본 — 대표 인물·사건의 구체 업적 매칭.
  "광개토대왕의 주요 정복 지역은?"
- 중급 (50%): 중1~중2 심화 — 정책의 원인·결과, 인물 간 구분.
  "광종이 노비안검법을 시행한 근본 목적은?"
- 고급 (20%): 중3~고1 — 사상적 배경·복합 원인·비교 분석.
  "갑신정변 주도 세력이 표방한 사상은?" (문명개화·입헌군주제)

【검증 체크리스트 — 생성 후 스스로 확인】
☐ 질문에 정답 단어가 그대로 들어있지 않은가?
☐ 공부 안 한 일반인이 찍어도 70% 이상 맞힐 수준이 아닌가?
☐ 이해/맥락/인과관계를 묻는가, 단순 암기인가?
☐ 위 5가지 "좋은 유형" 중 하나에 해당하는가?
→ 하나라도 실패하면 confidence_score 를 90 미만으로 낮춰 자동 폐기 유도.

출력은 JSON 만, 설명·인사말·마크다운 금지."""


def safe_print(*args, **kwargs):
    try:
        print(*args, **kwargs, flush=True)
    except (ValueError, OSError):
        pass


# ── 히스토리 ──────────────────────────────────────────────────────────────────
def _load_history() -> list:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save_history(history: list) -> None:
    HISTORY_FILE.write_text(
        json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ── 시대 선택 (결손 기반 로테이션) ─────────────────────────────────────────────
def _pick_era(history: list, lookback: int = 20, forbidden: set | None = None) -> str:
    """최근 lookback개 시대 분포 대비 결손이 큰 시대 선택. forbidden 내부 중복 차단용."""
    counts = {era: 0 for era in ERA_ORDER}
    for e in history[-lookback:]:
        era = e.get("era", "")
        if era in counts:
            counts[era] += 1
    deficits = {
        era: ERA_WEIGHTS[era] * lookback - counts[era]
        for era in ERA_ORDER
        if not forbidden or era not in forbidden
    }
    if not deficits:
        return random.choice(ERA_ORDER)
    max_d = max(deficits.values())
    top = [era for era, d in deficits.items() if d >= max_d - 0.3]
    return random.choice(top)


def _pick_difficulty() -> str:
    r = random.random()
    cum = 0.0
    for diff, w in DIFFICULTY_WEIGHTS.items():
        cum += w
        if r <= cum:
            return diff
    return "초급"


def _pick_quiz_type(last_type: str | None) -> str:
    """최근 유형과 반대로 — OX/4지선다 번갈아."""
    if last_type == "OX":
        return "4지선다"
    if last_type == "4지선다":
        return "OX"
    return random.choice(QUIZ_TYPES)


# ── JSON 스키마 검증 ──────────────────────────────────────────────────────────
def _validate_quiz_schema(data: dict, quiz_type: str) -> None:
    required = [
        "question", "answer", "explanation",
        "era", "difficulty", "type",
    ]
    for k in required:
        if k not in data:
            raise ValueError(f"필드 누락: {k}")

    if data["type"] != quiz_type:
        raise ValueError(f"type 불일치: 요청={quiz_type} / 응답={data['type']}")

    if quiz_type == "OX":
        if data["answer"] not in ("O", "X"):
            raise ValueError(f"OX answer는 'O' 또는 'X'여야 함: {data['answer']!r}")
    else:
        options = data.get("options")
        if not isinstance(options, list) or len(options) != 4:
            raise ValueError("4지선다는 options 4개 필요")
        if data["answer"] not in ("1", "2", "3", "4"):
            raise ValueError(f"4지선다 answer는 '1'~'4'여야 함: {data['answer']!r}")

    exp = data.get("explanation", "")
    if len(exp) > EXPLANATION_MAX:
        raise ValueError(f"explanation 너무 김 ({len(exp)}자, {EXPLANATION_MAX}자 이내)")
    if len(exp) < EXPLANATION_MIN:
        raise ValueError(f"explanation 너무 짧음 ({len(exp)}자, 최소 {EXPLANATION_MIN}자)")

    # 해설이 "정답은" 으로 시작하면 정답 음성과 중복 → 차단
    if exp.lstrip().startswith("정답은") or exp.lstrip().startswith("답은"):
        raise ValueError("explanation 이 '정답은' 으로 시작 — 해설은 근거부터 시작해야 함")

    # 질문 길이 하드 리밋 — TTS 5s 안에 읽히도록
    q = data.get("question", "")
    limit = QUESTION_MAX_OX if quiz_type == "OX" else QUESTION_MAX_MC
    if len(q) > limit:
        raise ValueError(f"question 너무 김 ({len(q)}자, {limit}자 이내)")

    # confidence_score 검증 — 95 미만 자동 폐기
    try:
        score = int(data.get("confidence_score", 0))
    except (TypeError, ValueError):
        raise ValueError(f"confidence_score 형식 오류: {data.get('confidence_score')!r}")
    if score < CONFIDENCE_MIN:
        raise ValueError(
            f"confidence_score 미달 ({score} < {CONFIDENCE_MIN}) — 문제 폐기"
        )
    data["confidence_score"] = score


# ── 프롬프트 빌더 ─────────────────────────────────────────────────────────────
def _build_prompt(
    era: str,
    difficulty: str,
    quiz_type: str,
    recent_questions: list[str],
    recent_titles: list[str],
    batch_questions: list[str] | None = None,
) -> str:
    batch_questions = batch_questions or []
    recent_q_block = "\n".join("- " + q for q in recent_questions) if recent_questions else "없음"
    recent_t_block = "\n".join("- " + t for t in recent_titles[-60:]) if recent_titles else "없음"
    batch_block = (
        "\n".join("- " + q for q in batch_questions)
        if batch_questions else "없음"
    )

    era_desc  = ERAS[era]
    diff_desc = DIFFICULTIES[difficulty]

    if quiz_type == "OX":
        schema_body = (
            '  "type": "OX",\n'
            f'  "question": "역사 사실 한 문장 진술 ({QUESTION_MAX_OX}자 이내, O/X로 답할 수 있어야 함)",\n'
            '  "answer": "O 또는 X",\n'
        )
        type_hint = (
            "OX 퀴즈 규칙:\n"
            "- question 은 '~은 ~이다', '~했다' 같은 진술문\n"
            "- 역사적 사실 기반, 명확한 O/X 판정 가능\n"
            f"- 반드시 {QUESTION_MAX_OX}자 이내 (TTS 5초 안에 읽혀야 함)\n"
        )
    else:
        schema_body = (
            '  "type": "4지선다",\n'
            f'  "question": "질문 한 줄 ({QUESTION_MAX_MC}자 이내)",\n'
            '  "options": ["1번 보기", "2번 보기", "3번 보기", "4번 보기"],\n'
            '  "answer": "1|2|3|4 중 정답 번호",\n'
        )
        type_hint = (
            "4지선다 규칙:\n"
            f"- question 은 짧고 명확한 한 줄 질문 ({QUESTION_MAX_MC}자 이내)\n"
            "- TTS 는 질문 본문만 읽고 보기는 자막으로만 표시됨 — 질문 자체가 짧아야 함\n"
            "- 보기 4개는 모두 같은 범주(사람/연도/장소/사건)로 통일\n"
            "- 보기 하나당 12자 이내\n"
            "- 오답은 그럴듯하되 명확히 틀린 것\n"
        )

    return f"""당신은 유튜브 역사퀴즈 채널 '{CHANNEL_NAME}({CHANNEL_TAGLINE})'의 퀴즈 기획자입니다.

[오늘의 문제 조건]
- 시대: {era} ({era_desc})
- 난이도: {difficulty} ({diff_desc})
- 유형: {quiz_type}

[절대 금지 — 이미 다룬 문제(히스토리)]
{recent_q_block}

[절대 금지 — 같은 에피소드 다른 문제(배치 내부)]
{batch_block}

[절대 금지 — 이미 업로드된 유튜브 제목]
{recent_t_block}

위 목록과 동일/유사한 주제는 절대 생성 금지.

{type_hint}

[해설(explanation) 작성 규칙 — 매우 중요]
- 13초 TTS 낭독용 — 한글 {EXPLANATION_MIN}~{EXPLANATION_MAX}자 분량(공백 포함)
- 정답은 영상에서 남성 음성이 별도로 공개함 — 해설에서 "정답은 ..." 문구는 절대 쓰지 말 것
- 첫 문장은 바로 근거·맥락부터 시작 (예: "삼국통일을 이룬 인물이 김유신이기 때문인데요, ...")
- 구조: 근거 한 줄 → 핵심 맥락 한 줄 → (선택) 흥미 포인트 한 줄
- 간결·명료·친근한 톤. 초등 고학년도 이해 가능
- 구체적 연도·인물 1개 이상 포함
- 지시문·마크다운·JSON 키 금지 — 바로 낭독 텍스트

[title / thumbnail_text]
- title: 20자 이내, 이모지 1~2개 (배치 전체의 제목이 아니므로 짧게)
- thumbnail_text: 12자 이내

[confidence_score 필드 — 중요]
- 0~100 정수로 자신이 생성한 문제의 역사 사실 정확도를 자가 평가
- 연도/인명/사건 관계가 100% 확실하면 95~100
- 추정·전설·논란 요소가 조금이라도 있으면 0~94 (이 경우 시스템이 자동 폐기)
- 확신 없으면 솔직히 낮은 점수 기입 — 시스템이 재시도함

[출력 형식 — 다른 말 없이 JSON만]
{{
  "title": "...",
  "thumbnail_text": "...",
{schema_body}  "explanation": "...",
  "era": "{era}",
  "difficulty": "{difficulty}",
  "confidence_score": 95~100,
  "tags": ["역사퀴즈", "{era}", "..."]
}}"""


# ── 팩트체크 (explanation 제외) ──────────────────────────────────────────────
def _factcheck(data: dict, client: OpenAI) -> dict:
    payload = json.dumps({
        "question": data.get("question"),
        "options":  data.get("options"),
        "answer":   data.get("answer"),
        "type":     data.get("type"),
        "era":      data.get("era"),
    }, ensure_ascii=False, indent=2)

    prompt = f"""역사 퀴즈 질문·보기·정답 팩트체크.

[검토 기준]
1. 질문 진술이 역사 사실과 다름
2. 정답이 틀렸거나 오답이 실제로는 맞는 경우
3. 야사·드라마·소설 내용을 사실로 서술

[출력 규칙]
- 문제 없으면: "통과"
- 문제 있으면: 수정 필요 필드만 JSON (question/options/answer 중)
- explanation 은 절대 수정 금지

[퀴즈]
{payload}"""

    try:
        resp = client.chat.completions.create(
            model=LLM_MODEL,
            max_tokens=400,
            messages=[
                {"role": "system", "content": (
                    "당신은 역사 팩트체크 전문가입니다. "
                    "'통과' 또는 JSON만 출력하며 안내문은 쓰지 않습니다."
                )},
                {"role": "user", "content": prompt},
            ],
        )
        result = resp.choices[0].message.content.strip()
        if result.startswith("통과"):
            return data
        m = re.search(r"\{[\s\S]*\}", result)
        if not m:
            return data
        patch = json.loads(m.group())
        merged = {**data, **patch}
        safe_print(f"  [팩트체크] 수정: {list(patch.keys())}", file=sys.stderr)
        return merged
    except Exception as e:
        safe_print(f"  [팩트체크] 오류 무시: {e}", file=sys.stderr)
        return data


# ── 해설 재맞춤 (길이 벗어나면 짧게·길게 재요청) ───────────────────────────────
def _refit_explanation(data: dict, client: OpenAI) -> str:
    current = data.get("explanation", "")
    if EXPLANATION_MIN <= len(current) <= EXPLANATION_MAX:
        return current

    direction = "더 간결하게 줄여" if len(current) > EXPLANATION_MAX else "더 풍부하게 늘려"
    prompt = (
        f"다음 역사 퀴즈 해설을 {direction} "
        f"한글 {EXPLANATION_MIN}~{EXPLANATION_MAX}자(공백 포함)로 다시 작성하세요.\n"
        "반드시 지킬 것:\n"
        "- 첫 문장을 '정답은', '답은' 같은 표현으로 시작하지 말 것 — 바로 근거·이유부터\n"
        "- 구체적 연도/인물 포함\n"
        "- 본문만 출력 (설명·인사말·JSON 키 금지)\n\n"
        f"[질문] {data.get('question','')}\n"
        f"[정답] {data.get('answer','')}\n"
        f"[현재 {len(current)}자]\n{current}"
    )
    try:
        resp = client.chat.completions.create(
            model=LLM_MODEL,
            max_tokens=500,
            messages=[
                {"role": "system", "content": "한국어 역사 나레이션 작가. 본문만 출력."},
                {"role": "user",   "content": prompt},
            ],
        )
        refit = resp.choices[0].message.content.strip()
        safe_print(f"  [재맞춤] {len(current)}자 → {len(refit)}자", file=sys.stderr)
        return refit
    except Exception as e:
        safe_print(f"  [재맞춤] 실패: {e}", file=sys.stderr)
        return current


# ── 단일 퀴즈 생성 ────────────────────────────────────────────────────────────
def _generate_one(
    era: str,
    difficulty: str,
    quiz_type: str,
    history: list,
    batch_questions: list[str],
    client: OpenAI,
) -> dict:
    recent_questions = [e.get("question", "") for e in history[-80:] if e.get("question")]
    recent_titles    = [e.get("title", "")    for e in history[-80:] if e.get("title")]

    prompt = _build_prompt(
        era, difficulty, quiz_type,
        recent_questions, recent_titles, batch_questions,
    )

    last_err: Exception | None = None
    rejected_log: list[dict] = []
    for attempt in range(4):
        try:
            resp = client.chat.completions.create(
                model=LLM_MODEL,
                max_tokens=900,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": QUIZ_SYSTEM_PROMPT},
                    {"role": "user",   "content": prompt},
                ],
            )
            raw = resp.choices[0].message.content.strip()
            data = json.loads(raw)

            data["era"]        = era
            data["difficulty"] = difficulty
            data["type"]       = quiz_type

            # 해설 길이 재맞춤 (벗어나면 1회 재요청)
            exp = data.get("explanation", "")
            if not (EXPLANATION_MIN <= len(exp) <= EXPLANATION_MAX):
                data["explanation"] = _refit_explanation(data, client)

            _validate_quiz_schema(data, quiz_type)

            # 팩트체크 — explanation 보존
            orig = data["explanation"]
            data = _factcheck(data, client)
            data["explanation"] = orig
            data["era"]         = era
            data["difficulty"]  = difficulty
            data["type"]        = quiz_type
            _validate_quiz_schema(data, quiz_type)

            return data

        except (json.JSONDecodeError, ValueError) as e:
            last_err = e
            # 폐기된 문제도 기록 — confidence 미달 케이스 추적용
            rejected_log.append({
                "attempt":    attempt + 1,
                "reason":     str(e),
                "question":   (data.get("question") if "data" in dir() and isinstance(data, dict) else None),
                "confidence": (data.get("confidence_score") if "data" in dir() and isinstance(data, dict) else None),
            })
            safe_print(f"  [퀴즈] 폐기/재시도 {attempt+1}/4: {e}", file=sys.stderr)
            time.sleep(2)

    if rejected_log:
        safe_print(
            f"  [퀴즈] ★ 총 폐기 {len(rejected_log)}건: "
            + " / ".join(
                f"#{r['attempt']}({r['confidence']}) {r['reason'][:40]}"
                for r in rejected_log
            ),
            file=sys.stderr,
        )
    raise RuntimeError(f"퀴즈 생성 실패 (4회, 폐기 {len(rejected_log)}건): {last_err}")


# ── 공개 API: 배치 생성 ───────────────────────────────────────────────────────
def generate_quiz_batch(
    n: int = NUM_QUIZZES,
    era_override: str | None = None,
    difficulty_override: str | None = None,
    type_override: str | None = None,
    verbose: bool = True,
) -> list[dict]:
    """n개 퀴즈를 생성해 list 로 반환. 시대/유형은 배치 내부에서 다양화."""
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY 미설정")

    client  = OpenAI(api_key=OPENAI_API_KEY)
    history = _load_history()
    used_eras: set[str] = set()
    last_type: str | None = None
    batch: list[dict] = []
    batch_questions: list[str] = []

    for i in range(n):
        # 시대 — override 있으면 그대로, 없으면 배치 내 중복 회피
        if era_override:
            era = era_override
        else:
            # 5문제이고 시대는 5개 — 한 배치 안에 각 시대 1번씩 나오도록
            era = _pick_era(history + [{"era": e} for e in used_eras], lookback=20, forbidden=used_eras if len(used_eras) < len(ERA_ORDER) else None)
        used_eras.add(era)

        difficulty = difficulty_override or _pick_difficulty()
        quiz_type  = type_override       or _pick_quiz_type(last_type)

        if verbose:
            safe_print(
                f"  [퀴즈 {i+1}/{n}] {era} / {difficulty} / {quiz_type}",
                file=sys.stderr,
            )

        quiz = _generate_one(era, difficulty, quiz_type, history, batch_questions, client)
        batch.append(quiz)
        batch_questions.append(quiz["question"])
        last_type = quiz_type

    # ── 히스토리 일괄 저장 ────────────────────────────────────────────────────
    base_episode = len(history) + 1
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    for i, q in enumerate(batch):
        history.append({
            "episode_num": base_episode,
            "quiz_idx":   i + 1,
            "era":        q["era"],
            "difficulty": q["difficulty"],
            "type":       q["type"],
            "question":   q["question"],
            "answer":     q["answer"],
            "confidence": q.get("confidence_score"),
            "title":      q.get("title", ""),
            "timestamp":  datetime.now().isoformat(),
        })
    _save_history(history)

    out_file = WORKSPACE / f"episode_{ts}.json"
    out_file.write_text(
        json.dumps({"episode_num": base_episode, "quizzes": batch}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    for q in batch:
        q["episode_num"] = base_episode

    if verbose:
        safe_print(f"  [배치] {n}문제 생성 완료 → episode {base_episode}", file=sys.stderr)
    return batch


# ── 에피소드 CTA 생성 ─────────────────────────────────────────────────────────
_CTA_FALLBACK = (
    "오늘 5문제 중 몇 개 맞히셨나요? 댓글로 점수 꼭 남겨주세요. "
    "오당역 구독과 알림 설정을 하시면 매일 새로운 역사 퀴즈가 올라옵니다. "
    "다음 에피소드는 더 재미있는 문제들로 찾아뵐게요. "
    "구독 버튼 눌러주시는 거 잊지 마시고, 오늘도 역사퀴즈왕 도전하세요!"
)


def generate_episode_cta(quizzes: list[dict]) -> str:
    """에피소드 아웃트로 CTA 텍스트 생성 (30초 분량, onyx 남성 낭독용)."""
    if not OPENAI_API_KEY:
        return _CTA_FALLBACK

    eras = list(dict.fromkeys(q.get("era", "") for q in quizzes))
    themes = ", ".join([f"{q['era']}({q['type']})" for q in quizzes[:5]])

    prompt = (
        f"유튜브 역사퀴즈 채널 '{CHANNEL_NAME}'의 30초 아웃트로 CTA 멘트를 작성하세요.\n\n"
        f"[오늘 다룬 문제 테마] {themes}\n"
        f"[시대 범위] {' · '.join(eras)}\n\n"
        f"[작성 규칙]\n"
        f"- 한글 {CTA_MIN}~{CTA_MAX}자 (공백 포함, 30초 TTS 분량)\n"
        f"- 남성 성우가 친근하게 낭독할 수 있는 자연스러운 문장\n"
        f"- 반드시 포함: (1) 점수 댓글 요청 (2) 구독·알림 요청 (3) 다음 편 기대감\n"
        f"- 오늘의 시대·테마를 한 번 자연스럽게 언급\n"
        f"- 본문만 출력, 인사말·설명·JSON 키 금지"
    )

    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        resp = client.chat.completions.create(
            model=LLM_MODEL,
            max_tokens=500,
            messages=[
                {"role": "system", "content": "한국어 유튜브 아웃트로 카피라이터. 본문만 출력."},
                {"role": "user", "content": prompt},
            ],
        )
        text = resp.choices[0].message.content.strip()
        if CTA_MIN <= len(text) <= CTA_MAX * 1.2:
            safe_print(f"  [CTA] {len(text)}자 생성", file=sys.stderr)
            return text
        safe_print(f"  [CTA] 길이 미달/초과({len(text)}자) — fallback 사용", file=sys.stderr)
    except Exception as e:
        safe_print(f"  [CTA] 생성 오류 ({e}) — fallback 사용", file=sys.stderr)
    return _CTA_FALLBACK


# ── 하위 호환 (단일 생성) ─────────────────────────────────────────────────────
def generate_quiz(
    era_override: str | None = None,
    difficulty_override: str | None = None,
    type_override: str | None = None,
    verbose: bool = True,
) -> dict:
    return generate_quiz_batch(
        n=1,
        era_override=era_override,
        difficulty_override=difficulty_override,
        type_override=type_override,
        verbose=verbose,
    )[0]
