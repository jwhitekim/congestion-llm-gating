---
paths:
  - "src/agent/**/*"
  - "src/datatypes.py"
---

# 선택적 LLM 단발 판정 구현(`agent/`) 세부 원칙

`agent/`는 기존 패키지명이다. 현재 시스템을 agent system 또는 에이전틱
워크플로우로 분류하는 근거로 사용하지 않는다. 논문 기준으로 이 패키지는
트리거된 구간의 텍스트 관측값을 받아 `assessment`와 대응 권고 수준인
`action`을 한 번 생성하는 LLM 판정 단계다.

## perception = observations, LLM = judgment

이 경계가 시스템 전체를 지탱한다. 위반하면 LLM이 도구를 우회해 직접 카운팅하는 문제(과거: 가시 인원 ~15명인데 track 42개 보고)가 재발한다.

- LLM은 **텍스트/숫자만** 입력받는다. 이미지·픽셀은 절대 전달하지 않는다(`agent/loop.py`의 `_facts_to_text`가 유일한 입력 경로). VLM을 쓰지 않는 건 우회 가능성을 구조적으로 차단하기 위함이지 비용 절감이 아니다.
- `agent/schema.py`의 `REQUIRED_FIELDS`에는 숫자 카운트 필드가 없다. 숫자는 **코드가 perception 관측값에서 직접 주입**한다(`loop.py`의 `validated["total_people"] = facts.current.total`). `_FORBIDDEN_NUMERIC` 방어를 제거하지 말 것. 단, `reasoning`은 자유 텍스트라 LLM이 그 안에 틀린 숫자를 재서술하는 것까지는 막지 못한다 — 알려진 한계.
- `tool_raw`는 호출 원본을 그대로 보존한다(연구용). 요약/폐기 금지.
- 새 tool의 `run(facts, **kwargs) -> dict`는 관측값만 반환. 판단(assessment/action)을 생산하면 안 된다.

## 노출 레지스트리 (`datatypes.py`)

`ALWAYS_VISIBLE` / `TOOL_ONLY` / `NOT_EXPOSED` 세 집합이 필드 노출 여부를 유일하게 결정한다(서로 배타적, assert 강제). 새 perception 필드를 추가할 때는 반드시 여기 먼저 등록 — `loop.py`나 tool 파일에서 개별적으로 노출 여부를 판단하지 말 것. `ALWAYS_VISIBLE`/`TOOL_ONLY` 분류 기준은 이 레지스트리가 자동으로 답을 주지 않는다 — 사람 판단 필요. `NOT_EXPOSED`는 로깅/연구용(`tracks`, `cv_elapsed_sec`, `timestamp`).

## registry + interface 패턴

현재 `TOOL_ONLY`와 tool-use 루프가 비어 있어 LLM은 외부 도구를 호출하지 않는다.
향후 도구 선택 기능을 구현할 때 tool-use 기반을 먼저 복원하고, 그 이후의 새
tool은 기존 파일(`loop.py`, `agent/tools/__init__.py`) 수정 없이
`agent/tools/`에 파일 하나만 추가하면 자동 등록돼야 한다.

```python
from . import register_tool

@register_tool(name="...", description="...", input_schema={...})
def my_tool(facts: AggregatedFacts, **kwargs) -> dict:
    ...
```

`agent/tools/__init__.py`가 `pkgutil.iter_modules`로 자동 import한다. 현재 registry가 존재한다는 사실을 실제 tool-use가 구현된 것으로 서술하지 않는다. 기반 복원 후에도 `loop.py`가 개별 도구를 import하거나 if/elif로 분기하면 이 패턴이 깨진다.

## action 레이어 (향후 확장 — 현재 미구현)

tool(read, LLM 루프 중 호출)과 action(write, 판단 후 부수효과)은 반대 성격이며 같은 레이어에 두지 않는다.

|  | tool | action |
|---|---|---|
| 목적 | 사실을 가져옴 | 세상을 바꿈 |
| 호출 시점 | LLM이 루프 중 | 판단 후 dispatcher |
| 위치 | `agent/tools/` | `action/` (agent 밖, src/ 최상위 형제) |

지금 `action` 필드는 실행된 행동이 아니라 LLM이 생산한 대응 권고 수준이다 — `main.py`는 출력·저장만 하고 dispatch하지 않는다. `action/` 디렉토리는 아직 없다. 상태 관리·도구 선택·후속 행동이 실제로 구현될 때에만 논문의 향후 과제인 에이전트형 시스템 분류를 재검토한다.

`session.json`/`results.jsonl` 기록은 action 예시가 아니다 — 기존 관측성 인프라이지 도메인 부수효과가 아니다.

## LLM 프로바이더 registry 패턴

`agent/providers/`는 tool과 같은 원칙(파일 추가 + registry 등록)을 벤더 선택에 적용한 것. `config.AGENT_PROVIDER`로 `_PROVIDERS` dict에서 클래스를 고른다. tool과 달리 **duck-typing**(`init_state`/`send`/`extract_text`/`extract_usage`/`is_retryable` 5개 메서드) — `agent/loop.py`는 어떤 프로바이더인지 모른다. 새 프로바이더 추가 시 `loop.py`를 건드리지 말 것.
