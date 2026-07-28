"""
simple_react.py — 최소 ReAct 학습 예제

프레임워크 없이, Claude API + while 루프만으로 만든 최소 에이전트.
이 한 파일이 "에이전트라는 기계"의 가장 작은 완성형이다.

독립 학습 예제이며 `src/main.py`의 규칙 기반 선택적 LLM 호출 워크플로우에는
import되거나 실행되지 않는다. 이 스크립트의 ReAct/tool-use를 논문 시스템의
현재 기능으로 서술하지 않는다.

실행 전:
    pip install anthropic
    export ANTHROPIC_API_KEY="sk-..."        # Windows(cmd): set ANTHROPIC_API_KEY=...
실행:
    python scripts/simple_react.py
"""

import os
import urllib.request
import urllib.parse
import json
import re
import anthropic

# ── 설정 (여기만 바꾸면 된다) ─────────────────────────────────────────
MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 1024
MAX_STEPS = 10          # 무한루프 방지용 안전장치 = '정지 조건'의 일부

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))      # ANTHROPIC_API_KEY 환경변수를 자동으로 읽는다


# ── 도구 2개 = 루프의 '행동(act)' 선택지 ──────────────────────────────
def calculator(expression: str) -> str:
    """간단한 수식 계산. 예: '2026 - 1397'  (학습용이라 보안은 최소한만)"""
    try:
        return str(eval(expression, {"__builtins__": {}}, {}))
    except Exception as e:
        return f"계산 오류: {e}"


def search_wikipedia(query: str) -> str:
    """위키피디아 검색. API 키 불필요, 표준 라이브러리만 사용."""
    url = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode({
        "action": "query", "list": "search", "srsearch": query,
        "format": "json", "srlimit": 3,
    })
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "bare-react-agent/0.1 (learning project)"
        })
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.load(r)
        hits = data["query"]["search"]
        if not hits:
            return "검색 결과 없음."
        strip = lambda s: re.sub(r"<.*?>", "", s)        # HTML 태그 제거
        return "\n".join(f"- {h['title']}: {strip(h['snippet'])}" for h in hits)
    except Exception as e:
        return f"검색 오류: {e}"


# 이름 → 실제 함수 매핑 (모델이 고른 이름으로 함수를 찾는다)
TOOLS = {
    "calculator": calculator,
    "search_wikipedia": search_wikipedia,
}

# 모델에게 넘길 도구 '명세'. 모델은 이 설명을 읽고 어떤 도구를 쓸지 고른다.
TOOL_SCHEMAS = [
    {
        "name": "calculator",
        "description": "수식을 계산한다. 예: '12 * (3 + 4)'",
        "input_schema": {
            "type": "object",
            "properties": {"expression": {"type": "string", "description": "파이썬 수식"}},
            "required": ["expression"],
        },
    },
    {
        "name": "search_wikipedia",
        "description": "위키피디아에서 사실/정보를 검색한다.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "검색어 (영어가 결과 많음)"}},
            "required": ["query"],
        },
    },
]


# ── 루프 = Step 1의 심장 ──────────────────────────────────────────────
def run_agent(question: str) -> str:
    # 이 messages 리스트가 곧 '컨텍스트 윈도우'다. 매 턴 계속 쌓인다.
    # → 길어지면 멍청해지는 지점. 나중에 Step 2가 손댈 바로 그 자리.
    messages = [{"role": "user", "content": question}]

    for step in range(1, MAX_STEPS + 1):

        # ── 1. 추론(reason): 모델이 생각하고 다음 행동을 정한다 ──
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            tools=TOOL_SCHEMAS,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})

        print(f"response.content: {response.content}")   # (디버그용) 모델이 뭘 생각했는지 전체 블록을 보여준다
        
        # 모델의 '생각'(텍스트 블록)을 화면에 보여준다 — 루프를 눈으로 보기 위함
        for block in response.content:
            if block.type == "text" and block.text.strip():
                print(f"\n[{step}]z` 🧠 {block.text.strip()}")

        # ── 정지 조건: 도구를 더 안 부르면 = 끝났다는 뜻 ──
        #    (나중에 Reflexion은 '끝'이라고 판단하기 직전에 반성 스텝을 끼워넣는다)
        if response.stop_reason != "tool_use":
            return "".join(b.text for b in response.content if b.type == "text")

        # ── 2. 행동(act) + 3. 관찰(observe): 도구 실행하고 결과를 되먹인다 ──
        results = []
        for block in response.content:
            if block.type == "tool_use":
                print(f"    🔧 {block.name}({block.input})")
                output = TOOLS[block.name](**block.input)      # 실제 실행
                print(f"    📥 {output[:200]}")
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": output,
                })
        messages.append({"role": "user", "content": results})  # ↻ 결과를 넣고 1번으로 복귀

    return "최대 스텝 도달 — 끝내지 못함."


if __name__ == "__main__":
    # 이 질문은 일부러 두 도구를 모두 강제한다:
    #   위키로 세종대왕 출생연도(1397) 찾기  →  계산기로 2026 - 1397
    question = "세종대왕이 태어난 해부터 2026년까지 몇 년이 지났는지 계산해줘."
    print(f"❓ 질문: {question}")
    answer = run_agent(question)
    print(f"\n✅ 최종 답: {answer}")
