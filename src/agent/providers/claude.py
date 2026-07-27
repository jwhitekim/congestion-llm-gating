"""
선택적 LLM 단발 판정을 위한 Anthropic Claude 프로바이더
(tool 없음, datatypes.TOOL_ONLY 참고).
이 클래스는 다른 provider와 인터페이스를 상속하지 않는다 — init_state/send/
extract_text/extract_usage/is_retryable 5개 메서드만 맞추면 agent/loop.py가
그대로 돌린다(duck typing).
"""

import anthropic

import config


class ClaudeProvider:
    def __init__(self):
        self._client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY, timeout=30.0)

    def init_state(self, user_message: str) -> list[dict]:
        return [{"role": "user", "content": user_message}]

    def send(self, system_prompt: str, state: list[dict]):
        return self._client.messages.create(
            model=config.ANTHROPIC_MODEL,
            # scripts/probe_agent.py 실측 기준 왕복 1회당 최대 관측 출력 토큰은
            # 720(구 프롬프트, congestion_level/local_hotspots 포함) / 622(신 프롬프트,
            # 압축 후) — 896은 그 위에 ~24% 여유를 둔 상한이다. 1024는 근거 없이
            # 설정된 값이었다.
            max_tokens=896,
            system=system_prompt,
            messages=state,
        )

    def extract_text(self, response) -> str:
        if response.stop_reason != "end_turn":
            return ""  # 비정상 stop_reason
        return "".join(block.text for block in response.content if hasattr(block, "text"))

    def extract_usage(self, response) -> dict:
        return {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "stop_reason": response.stop_reason,
        }

    def is_retryable(self, exc: Exception) -> bool:
        """API 레벨 실패(네트워크/타임아웃/rate limit/서버 오류)만 재시도 대상."""
        return isinstance(exc, (
            anthropic.APIConnectionError,   # 네트워크 오류 (APITimeoutError 포함)
            anthropic.RateLimitError,       # 429
            anthropic.InternalServerError,  # 5xx
            anthropic.OverloadedError,      # 529 overloaded
        ))
