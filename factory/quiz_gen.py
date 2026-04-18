"""
오당역 — Quiz Generator
GPT-4o-mini로 OX / 4지선다 역사 퀴즈 생성
- 시대 로테이션: 삼국 / 고려 / 조선 / 근현대 / 세계사
- 난이도: 초급 60% / 중급 30% / 고급 10%
- 유형: OX / 4지선다 번갈아
- 중복 방지: quiz_history.json + 유튜브 제목 금지 목록
- 팩트체크 2-pass
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
)

HISTORY_FILE = REPO_ROOT / "quiz_history.json"


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
def _pick_era(history: list, lookback: int = 20) -> str:
    """최근 lookback개 시대 분포 대비 결손이 큰 시대 선택."""
    counts = {era: 0 for era in ERA_ORDER}
    for e in history[-lookback:]:
        era = e.get("era", "")
        if era in counts:
            counts[era] += 1
    deficits = {
        era: ERA_WEIGHTS[era] * lookback - counts[era]
        for era in ERA_ORDER
    }
    max_d = max(deficits.values())
    top = [era for era, d in deficits.items() if d >= max_d - 0.3]
    return random.choice(top)


# ── 난이도 선택 (가중 랜덤) ────────────────────────────────────────────────────
def _pick_difficulty() -> str:
    r = random.random()
    cum = 0.0
    for diff, w in DIFFICULTY_WEIGHTS.items():
        cum += w
        if r <= cum:
            return diff
    return "초급"


# ── 유형 선택 (히스토리 기반 번갈아) ───────────────────────────────────────────
def _pick_quiz_type(history: list) -> str:
    """최근 유형과 반대로 — OX/4지선다 번갈아."""
    if not history:
        return random.choice(QUIZ_TYPES)
    last_type = history[-1].get("type", "")
    if last_type == "OX":
        return "4지선다"
    if last_type == "4지선다":
        return "OX"
    return random.choice(QUIZ_TYPES)


# ── JSON 스키마 검증 ──────────────────────────────────────────────────────────
def _validate_quiz_schema(data: dict, quiz_type: str) -> None:
    required = [
        "title", "thumbnail_text", "question", "answer",
        "explanation", "era", "difficulty", "type", "tags",
    ]
    for k in required:
        if k not in data:
            raise ValueError(f"필드 누락: {k}")

    if data["type"] != quiz_type:
        raise ValueError(f"type 불일치: 요청={quiz_type} / 응답={data['type']}")

    if quiz_type == "OX":
        if data["answer"] not in ("O", "X"):
            raise ValueError(f"OX answer는 'O' 또는 'X'여야 함: {data['answer']!r}")
    else:  # 4지선다
        options = data.get("options")
        if not isinstance(options, list) or len(options) != 4:
            raise ValueError("4지선다는 options 4개 필요")
        if data["answer"] not in ("1", "2", "3", "4"):
            raise ValueError(f"4지선다 answer는 '1'~'4'여야 함: {data['answer']!r}")

    # 해설은 TTS 100초 안에 끝나야 → 한글 800자 이내
    exp = data.get("explanation", "")
    if len(exp) > 800:
        raise ValueError(f"explanation 너무 김 ({len(exp)}자, 800자 이내)")
    if len(exp) < 300:
        raise ValueError(f"explanation 너무 짧음 ({len(exp)}자, 최소 300자)")


# ── 프롬프트 빌더 ─────────────────────────────────────────────────────────────
def _build_prompt(
    era: str,
    difficulty: str,
    quiz_type: str,
    recent_questions: list[str],
    recent_titles: list[str],
) -> str:
    recent_q_block = "\n".join("- " + q for q in recent_questions) if recent_questions else "없음"
    recent_t_block = "\n".join("- " + t for t in recent_titles[-60:]) if recent_titles else "없음"

    era_desc  = ERAS[era]
    diff_desc = DIFFICULTIES[difficulty]

    if quiz_type == "OX":
        schema_body = (
            '  "type": "OX",\n'
            '  "question": "역사 사실 한 문장 진술 (20자 이내, O/X로 답할 수 있어야 함)",\n'
            '  "answer": "O 또는 X",\n'
        )
        type_hint = (
            "OX 퀴즈 규칙:\n"
            "- question 은 '~은 ~이다', '~했다' 같은 진술문\n"
            "- 역사적 사실 기반, 명확한 O/X 판정이 가능해야 함\n"
            "- 20자 이내로 짧고 읽기 쉽게\n"
            "- 반전·함정 있는 진술이 재밌음 (예: '세종대왕은 한글을 혼자 만들었다' → X)\n"
        )
    else:
        schema_body = (
            '  "type": "4지선다",\n'
            '  "question": "질문 한 줄 (25자 이내)",\n'
            '  "options": ["1번 보기", "2번 보기", "3번 보기", "4번 보기"],\n'
            '  "answer": "1|2|3|4 중 정답 번호",\n'
        )
        type_hint = (
            "4지선다 규칙:\n"
            "- question 은 짧고 명확한 한 줄 질문 (25자 이내)\n"
            "- 보기 4개는 모두 같은 범주(사람/연도/장소/사건)로 통일\n"
            "- 보기 하나당 12자 이내 — 썸네일에도 들어갈 수 있어야 함\n"
            "- 오답은 그럴듯하되 명확히 틀린 것\n"
        )

    return f"""당신은 유튜브 역사퀴즈 채널 '{CHANNEL_NAME}({CHANNEL_TAGLINE})'의 퀴즈 기획자입니다.

[오늘의 문제 조건]
- 시대: {era} ({era_desc})
- 난이도: {difficulty} ({diff_desc})
- 유형: {quiz_type}

[절대 금지 — 이미 다룬 문제]
{recent_q_block}

[절대 금지 — 이미 업로드된 유튜브 제목]
{recent_t_block}

위 목록과 동일/유사한 주제·제목은 절대 생성하지 마세요.

{type_hint}

[해설(explanation) 작성 규칙]
- 100초 TTS 낭독용 — 한글 600~750자 분량 (공백 포함)
- 구조: (1) 정답 공개 한 문장 (2) 왜 그것이 정답인지 핵심 설명 (3) 관련 역사적 맥락·배경
  (4) 흥미로운 뒷이야기·에피소드 (5) 구독 CTA 한 문장
- 첫 문장은 반드시 "정답은 {{X}}입니다." 로 시작
- 낭독 톤: 친근한 역사 선생님. 초등 고학년~성인 모두 이해 가능하게
  "사실은요", "믿기 어렵겠지만", "재밌는 건" 같은 흥미 유발 표현 적극 활용
- 구체적 연도·인물·사건을 반드시 1개 이상 포함 — 해설에 밀도 있는 정보를 담을 것
- 맨 끝 CTA 예시: "매일 새 문제 올라옵니다. 오당역 구독하고 역사퀴즈왕 도전하세요!"
- 지시문·마크다운·JSON 키 절대 금지 — 바로 낭독 텍스트

[title / thumbnail_text 작성 규칙]
- title: 20자 이내, 이모지 1~2개, 클릭 유도형 (예: "삼국통일 한 왕은 누구?🤔")
- thumbnail_text: 12자 이내, 썸네일에 들어갈 한 줄 훅 (예: "이 중 정답은?")

[출력 형식 — 다른 말 없이 JSON만]
{{
  "title": "...",
  "thumbnail_text": "...",
{schema_body}  "explanation": "...",
  "era": "{era}",
  "difficulty": "{difficulty}",
  "tags": ["역사퀴즈", "{era}", "..."]
}}"""


# ── 해설 확장 ─────────────────────────────────────────────────────────────────
def _expand_explanation(data: dict, target_min: int, client: OpenAI) -> str:
    """해설이 너무 짧을 때 사실 유지하며 확장."""
    current = data.get("explanation", "")
    prompt = (
        "다음 역사 퀴즈 해설이 너무 짧습니다. "
        f"역사 사실은 그대로 유지하되 배경·맥락·뒷이야기를 추가해 "
        f"한글 {target_min}~750자 분량(공백 포함)으로 확장해주세요. "
        "첫 문장 '정답은 ...' 과 끝 문장(구독 CTA)은 반드시 유지.\n\n"
        f"[질문] {data.get('question','')}\n"
        f"[정답] {data.get('answer','')}\n"
        f"[현재 해설 ({len(current)}자)]\n{current}\n\n"
        "확장된 해설 본문만 출력. 설명·인사말·JSON 키 금지."
    )
    try:
        resp = client.chat.completions.create(
            model=LLM_MODEL,
            max_tokens=1500,
            messages=[
                {"role": "system", "content": "한국어 역사 나레이션 작가. 본문만 출력."},
                {"role": "user",   "content": prompt},
            ],
        )
        expanded = resp.choices[0].message.content.strip()
        safe_print(f"  [확장] {len(current)}자 → {len(expanded)}자", file=sys.stderr)
        return expanded if len(expanded) >= len(current) else current
    except Exception as e:
        safe_print(f"  [확장] 실패 — 원본 유지: {e}", file=sys.stderr)
        return current


# ── 팩트체크 (explanation 제외) ──────────────────────────────────────────────
def _factcheck(data: dict, client: OpenAI) -> dict:
    """GPT-4o-mini 2차 검증 — 질문/보기/정답만 사실 오류 확인. 해설은 건드리지 않음."""
    payload = json.dumps({
        "question": data.get("question"),
        "options":  data.get("options"),
        "answer":   data.get("answer"),
        "type":     data.get("type"),
        "era":      data.get("era"),
    }, ensure_ascii=False, indent=2)

    prompt = f"""역사 퀴즈 질문·보기·정답의 팩트체크.

[검토 기준]
1. 질문 진술이 역사 사실과 다름
2. 보기 중 정답이 틀렸거나 오답이 실제로는 맞는 경우
3. 야사·드라마·소설 내용을 사실로 서술

[출력 규칙]
- 문제 없으면: "통과" 한 단어
- 문제 있으면: 수정 필요한 필드만 JSON (question/options/answer 중)
- explanation(해설)은 절대 수정하지 말 것 — 이 필드는 검토 대상 아님

[퀴즈]
{payload}"""

    try:
        resp = client.chat.completions.create(
            model=LLM_MODEL,
            max_tokens=800,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "당신은 역사 팩트체크 전문가입니다. 안내문·설명문 없이 "
                        "'통과' 또는 JSON만 출력합니다."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        )
        result = resp.choices[0].message.content.strip()
        if result.startswith("통과"):
            safe_print("  [팩트체크] ✓ 통과", file=sys.stderr)
            return data

        m = re.search(r"\{[\s\S]*\}", result)
        if not m:
            return data
        patch = json.loads(m.group())
        merged = {**data, **patch}
        safe_print(f"  [팩트체크] 수정 적용: {list(patch.keys())}", file=sys.stderr)
        return merged
    except Exception as e:
        safe_print(f"  [팩트체크] 오류 무시: {e}", file=sys.stderr)
        return data


# ── 메인 생성 함수 ────────────────────────────────────────────────────────────
def generate_quiz(
    era_override: str | None = None,
    difficulty_override: str | None = None,
    type_override: str | None = None,
    verbose: bool = True,
) -> dict:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY 가 설정되지 않았습니다.")

    history = _load_history()
    era        = era_override        or _pick_era(history)
    difficulty = difficulty_override or _pick_difficulty()
    quiz_type  = type_override       or _pick_quiz_type(history)

    if verbose:
        safe_print(
            f"  [퀴즈] 시대={era} / 난이도={difficulty} / 유형={quiz_type}",
            file=sys.stderr,
        )

    recent_questions = [
        e.get("question", "") for e in history[-80:] if e.get("question")
    ]
    recent_titles = [e.get("title", "") for e in history[-80:] if e.get("title")]

    prompt = _build_prompt(era, difficulty, quiz_type, recent_questions, recent_titles)
    client = OpenAI(api_key=OPENAI_API_KEY)

    last_err: Exception | None = None
    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model=LLM_MODEL,
                max_tokens=1200,
                response_format={"type": "json_object"},
                messages=[{"role": "user", "content": prompt}],
            )
            raw = resp.choices[0].message.content.strip()
            data = json.loads(raw)

            # 우리가 결정한 메타값을 강제 주입 — 모델이 누락/변조해도 무관
            data["era"]        = era
            data["difficulty"] = difficulty
            data["type"]       = quiz_type

            # 해설 길이 부족 시 확장 1회
            if len(data.get("explanation", "")) < 600:
                data["explanation"] = _expand_explanation(data, 600, client)

            _validate_quiz_schema(data, quiz_type)

            # 팩트체크 — explanation 은 건드리지 않음
            orig_explanation = data["explanation"]
            data = _factcheck(data, client)
            data["explanation"] = orig_explanation
            data["era"]         = era
            data["difficulty"]  = difficulty
            data["type"]        = quiz_type
            _validate_quiz_schema(data, quiz_type)

            # 히스토리 저장
            episode_num = len(history) + 1
            history.append({
                "episode_num": episode_num,
                "era":        era,
                "difficulty": difficulty,
                "type":       quiz_type,
                "question":   data["question"],
                "answer":     data["answer"],
                "title":      data["title"],
                "timestamp":  datetime.now().isoformat(),
            })
            _save_history(history)

            ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_file = WORKSPACE / f"quiz_{ts}.json"
            out_file.write_text(
                json.dumps(
                    {**data, "episode_num": episode_num},
                    ensure_ascii=False, indent=2,
                ),
                encoding="utf-8",
            )

            return {
                **data,
                "episode_num": episode_num,
                "output_file": str(out_file),
            }

        except (json.JSONDecodeError, ValueError) as e:
            last_err = e
            safe_print(
                f"  [퀴즈] 파싱/검증 실패 (재시도 {attempt+1}/3): {e}",
                file=sys.stderr,
            )
            time.sleep(2)

    raise RuntimeError(f"퀴즈 생성 실패 (3회): {last_err}")
