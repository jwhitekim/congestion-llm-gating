"""
선택적 LLM 단발 판정을 위한 Google Gemini 프로바이더
(Interactions API, google-genai SDK, tool 없음, datatypes.TOOL_ONLY 참고).
이 클래스는 init_state/send/extract_text/extract_usage/is_retryable 5개
메서드만 맞추면 되고 별도 인터페이스는 상속하지 않는다(duck typing).
"""

import httpx
import requests
from google import genai
from google.genai import errors as genai_errors

import config


class GeminiProvider:
    def __init__(self):
        self._client = genai.Client(api_key=config.GEMINI_API_KEY)

    def init_state(self, user_message: str) -> dict:
        return {"input": user_message}

    def send(self, system_prompt: str, state: dict):
        return self._client.interactions.create(
            model=config.GEMINI_MODEL,
            input=state["input"],
            system_instruction=system_prompt,
        )

    def extract_text(self, response) -> str:
        return response.output_text or ""

    def extract_usage(self, response) -> dict:
        usage = response.usage
        return {
            "input_tokens": usage.total_input_tokens if usage else None,
            "output_tokens": usage.total_output_tokens if usage else None,
            "stop_reason": response.status,
        }

    def is_retryable(self, exc: Exception) -> bool:
        """API 레벨 실패(네트워크/타임아웃/rate limit/서버 오류)만 재시도 대상."""
        if isinstance(exc, genai_errors.ServerError):  # 5xx
            return True
        if isinstance(exc, genai_errors.ClientError):
            return exc.code == 429  # rate limit
        return isinstance(exc, (httpx.TransportError, requests.exceptions.ConnectionError, requests.exceptions.Timeout))
