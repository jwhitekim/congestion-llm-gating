"""
규칙 기반 이벤트가 발생한 구간의 선택적 LLM 단발 판정.

LLM은 판단(assessment, reasoning, action)만 생산한다.
숫자 사실(total_people, density 등)은 LLM 출력 스키마에 없으며
코드가 facts에서 직접 주입한다.

외부 tool 호출과 self-correction 루프는 없다. 선택된 세그먼트마다 판단은
한 번 생성하지만, 일시적인 API 실패에는 전송을 재시도할 수 있다.
agent/tools/의 registry는 남아 있으나 현재 provider/loop 경로와 연결돼 있지 않다.
"""

import json
import time

import config
import datatypes
from datatypes import AggregatedFacts
from . import prompt, schema
from .providers import get_provider

_provider = get_provider()

# ALWAYS_VISIBLE은 set이라 순서가 없다 — 텍스트 표시 순서는 여기서 고정한다.
# datatypes.ALWAYS_VISIBLE과 어긋나면(필드 추가/삭제 시 여기 갱신을 잊으면)
# import 시점에 바로 알 수 있도록 assert로 동기화한다.
_TEXT_FIELD_ORDER = (
    "total", "density", "density_delta_ratio", "avg_speed", "speed_trend",
    "zone_counts", "zone_density", "concentration", "level", "density_slope",
)
assert set(_TEXT_FIELD_ORDER) == datatypes.ALWAYS_VISIBLE, (
    "loop.py의 _TEXT_FIELD_ORDER가 datatypes.ALWAYS_VISIBLE과 어긋남"
)

_FIELD_LABELS = {
    "total": "총 인원",
    "density": "밀도(density)",
    "density_delta_ratio": "밀도 변화율(직전 평균 대비)",
    "avg_speed": "평균 속도",
    "speed_trend": "속도 추세(speed_trend)",
    "zone_counts": "구역별 인원",
    "zone_density": "구역별 밀도",
    "concentration": "집중도(concentration, HHI)",
    "level": "혼잡 수준",
    "density_slope": "밀도 추세(density_slope)",
}


def _format_field(field: str, value) -> str:
    if field == "zone_counts":
        return "  ".join(f"{z}={n}명" for z, n in value.items())
    if field == "zone_density":
        return "  ".join(f"{z}={d:.2f}" for z, d in value.items())
    if field == "total":
        return f"{value}명"
    if field == "avg_speed":
        return f"{value:.2f} px/s"
    if field == "density_delta_ratio":
        return f"{value:.2f}x"
    if field in ("density_slope", "speed_trend"):
        return f"{value:+.4f}"
    if field in ("density", "concentration"):
        return f"{value:.2f}"
    return str(value)


def _send_with_retry(provider, system_prompt: str, state, log=None):
    """
    provider.send()를 실행하고, provider.is_retryable()이 참인 예외에 한해
    지수 백오프로 재시도한다. LLM의 판단 자체를 재시도하는 것이 아니라
    API 왕복이 네트워크/rate limit/서버 오류로 실패했을 때만 개입한다 —
    reflection/self-correction과는 무관하다.
    """
    delay = config.AGENT_RETRY_BACKOFF_SEC
    attempt = 0
    while True:
        try:
            return provider.send(system_prompt, state)
        except Exception as exc:
            if attempt >= config.AGENT_MAX_RETRIES or not provider.is_retryable(exc):
                raise
            attempt += 1
            if log is not None:
                log.warning(
                    f"API 호출 실패 ({type(exc).__name__}: {exc}) — "
                    f"재시도 {attempt}/{config.AGENT_MAX_RETRIES}, {delay:.1f}초 후"
                )
            time.sleep(delay)
            delay *= 2


def _facts_to_text(facts: AggregatedFacts) -> str:
    lines = ["[집계 사실]"]
    for field in _TEXT_FIELD_ORDER:
        value = getattr(facts.current, field) if hasattr(facts.current, field) else getattr(facts, field)
        lines.append(f"- {_FIELD_LABELS[field]}: {_format_field(field, value)}")
    return "\n".join(lines) + "\n"


def _compute_local_hotspots(facts: AggregatedFacts, zone_max: float) -> list[str]:
    """
    zone_max를 초과하는 구역을 나열한다. trigger/rules.py의 hotspot 조건과 동일한
    순수 사실 조회이므로 코드가 계산해 주입한다 — LLM이 재생산하지 않는다.

    zone_max는 호출부(main.py)가 rules.evaluate()의 thresholds["zone_max"]를 그대로
    전달한 값이다 — config.ZONE_MAX를 여기서 직접 읽지 않는다. 두 곳이 각자 읽으면
    rules.py가 percentile 기반 동적 임계값으로 바뀐 뒤에도 여기는 옛 고정값을 써서
    같은 세그먼트의 trigger_reason과 local_hotspots가 서로 다른 기준으로 어긋나는
    문제가 있었다(실측) — 그래서 rules.py를 유일한 계산 출처로 고정한다.
    """
    return [
        f"{zone}구역 {count}명"
        for zone, count in facts.current.zone_counts.items()
        if count > zone_max
    ]


def run(
    facts: AggregatedFacts,
    trigger_name: str,
    trigger_reason: str,
    zone_max: float,
    log=None,
    include_trigger_reason: bool = True,
) -> dict:
    """
    트리거 발생 시 텍스트 LLM을 1회 호출해 판정한다 (single-shot, tool 없음).

    trigger_reason: trigger/rules.py가 산출한 정량적 트리거 근거 문자열
    (예: "density 22.9 > avg × 1.4, ratio=1.60"). 이미 문자열이라 숫자
    hallucination 방어(_FORBIDDEN_NUMERIC)와는 무관하고, trigger가 이미 계산한
    사실을 그대로 전달하는 것이므로 perception=observations/LLM=judgment
    경계도 깨지 않는다.

    zone_max: rules.evaluate()가 반환한 thresholds["zone_max"](percentile 기반
    동적값, 콜드스타트 중엔 config.ZONE_MAX fallback)를 그대로 받는다.
    local_hotspots 계산에 쓰는 임계값을 rules.py와 동일하게 맞추기 위함 —
    config.ZONE_MAX를 여기서 다시 읽지 않는다(_compute_local_hotspots 참고).

    include_trigger_reason: False면 프롬프트에서 trigger_reason 문장을 뺀다
    (trigger_name만 남김). trigger_reason 주입 효과를 A/B로 비교하기 위한
    연구용 스위치 — scripts/ab_trigger_reason.py 전용, 기본값 True라 기존
    호출부(main.py 등)는 영향 없음.

    log: main.py의 GetLogger 인스턴스(선택). API 재시도 발생 시 log.warning으로
    기록한다 — 없으면 재시도는 조용히 진행된다(로깅만 생략, 재시도 자체는 동작).

    반환 dict:
      - LLM 판단 필드 (schema.py 참고: assessment/distribution_summary/reasoning/action)
      - total_people, density, congestion_level, local_hotspots: 코드가 facts에서
        주입 (LLM 생산 아님)
      - tool_called, tool_raw, duplicate_tool_calls: 과거 결과 스키마 호환용
        False/[]/False. 현재 tool 호출 기록이 아니다
      - api_call_breakdown: 성공 응답의 시간/토큰/stop_reason을 담은 원소 1개.
        재시도가 있었다면 elapsed_sec에는 재시도와 backoff가 포함될 수 있지만
        각 실패 시도는 별도 원소로 기록하지 않는다
    """
    trigger_line = (
        f"트리거 발생: {trigger_name} ({trigger_reason})"
        if include_trigger_reason
        else f"트리거 발생: {trigger_name}"
    )
    user_message = f"{trigger_line}\n\n{_facts_to_text(facts)}\n위 사실을 바탕으로 상황을 판정하십시오."

    state = _provider.init_state(user_message)

    call_start = time.perf_counter()
    response = _send_with_retry(_provider, prompt.SYSTEM_PROMPT, state, log=log)
    call_elapsed = time.perf_counter() - call_start

    usage = _provider.extract_usage(response)
    api_call_log = [
        {
            "elapsed_sec": round(call_elapsed, 3),
            "input_tokens": usage["input_tokens"],
            "output_tokens": usage["output_tokens"],
            "stop_reason": usage["stop_reason"],
        }
    ]

    text = _provider.extract_text(response)

    try:
        start = text.find("{")
        end = text.rfind("}") + 1
        parsed = json.loads(text[start:end])
        validated = schema.validate(parsed)
    except (json.JSONDecodeError, ValueError) as e:
        validated = {
            "assessment": "caution",
            "distribution_summary": "파싱 실패",
            "reasoning": f"LLM 응답 파싱 오류: {e}",
            "action": "monitor",
        }

    # 숫자/등급 사실은 코드가 주입 — LLM이 생산한 값이 아님
    validated["total_people"] = facts.current.total
    validated["density"] = facts.current.density
    validated["congestion_level"] = facts.level
    validated["local_hotspots"] = _compute_local_hotspots(facts, zone_max)
    validated["trigger"] = trigger_name
    validated["tool_called"] = False
    validated["tool_raw"] = []
    validated["api_call_breakdown"] = api_call_log
    validated["duplicate_tool_calls"] = False
    return validated
