"""
LLM 프로바이더 레지스트리.

config.AGENT_PROVIDER 값("anthropic" | "gemini")에 따라 provider를 고른다.
provider 클래스는 별도 인터페이스를 상속하지 않는다 — init_state/send/
extract_text/extract_usage/is_retryable 5개 메서드만 구현하면 agent/loop.py의
선택적 LLM 단발 호출이 그대로 동작한다(duck typing).
is_retryable(exc)은 send()가 던진 예외가 API 레벨 일시 오류(네트워크/rate
limit/서버 오류)인지 판정한다 — loop.py는 이 판정에 따라서만 재시도하고,
어떤 예외 클래스가 재시도 대상인지는 전혀 모른다.

현재 provider 인터페이스에는 tool-use 메서드가 없고 agent/loop.py에도
tool-use 루프가 없다. 도구 선택은 논문이 향후 확장으로 제시한 기능이다.

새 프로바이더를 추가하려면 이 패키지에 파일을 추가해 위 5개 메서드를 구현한
클래스를 만들고 아래 _PROVIDERS에 한 줄만 등록하면 된다. loop.py는 건드릴
필요 없다.
"""

import config
from .claude import ClaudeProvider
from .gemini import GeminiProvider

_PROVIDERS = {
    "anthropic": ClaudeProvider,
    "gemini": GeminiProvider,
}


def get_provider() -> ClaudeProvider | GeminiProvider:
    provider_cls = _PROVIDERS.get(config.AGENT_PROVIDER)
    if provider_cls is None:
        raise ValueError(
            f"Unknown AGENT_PROVIDER: {config.AGENT_PROVIDER!r} "
            f"(choices: {sorted(_PROVIDERS)})"
        )
    return provider_cls()
