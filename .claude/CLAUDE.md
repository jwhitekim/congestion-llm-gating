# congestion-llm-gating — 아키텍처 및 논문 서술 원칙

이 문서는 congestion-llm-gating을 수정/확장할 때 지켜야 할 설계 원칙이다.
코드를 고치기 전에 먼저 읽을 것. 여기 적힌 경계를 어기면 시스템 전체의 전제가 무너진다.
`src/agent/`, `src/datatypes.py`, `src/trigger/` 작업 시에는 `.claude/rules/`의 해당 문서도 함께 읽는다.

## 실행
- `make run` / `make run VIDEO=<path>` — PYTHONPATH=src python src/main.py 실행
- `make dash` / `make dash-build` — 대시보드

## 0. 용어 정의

- **규칙 기반 선택적 LLM 호출 워크플로우(rule-gated selective LLM invocation workflow)** — 현재 시스템 전체를 가리키는 논문 기준 명칭. `main.py`가 perception → trigger → 선택적 LLM 단발 판정을 오케스트레이션한다.
- **인지 계층(perception layer)** — 모든 구간에서 사람 검출·추적과 구역별 밀도, 속도 및 변화 추세를 계산하는 코드 계층.
- **규칙 기반 이벤트 게이트(rule-based event gate)** — 관측값으로 LLM 호출 여부를 결정하는 코드 계층.
- **LLM 단발 판정(single-shot LLM judgment)** — 트리거된 구간의 구조화된 텍스트 관측값을 받아 `assessment`와 권고 수준인 `action`을 한 번 생성하는 단계.
- **tool** — `agent/tools/`에 등록되어 사실을 조회만 하는 컴포넌트(현재 비어있음). 판단하지 않는다.

현재 구현을 **agent system**, **자율 에이전트**, **에이전틱 워크플로우**라고 부르지 않는다. `agent/`, `agent_output`, `AGENT_PROVIDER`의 `agent`는 기존 코드 호환성을 위한 구현 이름일 뿐 시스템 분류가 아니다. NCISS 논문은 현재 구현을 **training-free 워크플로우**로 설명하며, 상태 관리·도구 선택·후속 행동을 포함하는 **에이전트형 혼잡도 모니터링 시스템**은 향후 확장으로만 제시한다.

`action`은 실행된 행동이 아니라 LLM이 출력한 **대응 권고 수준**이다. 현재 코드는 실제 후속 행동을 실행하지 않는다.

### 논문 주장 경계

- 실험에서 400개 구간 중 101개만 호출되어 always-call 대비 **호출량이 74.8% 감소**했다. 실제 비용·토큰·지연이 74.8% 감소했다고 바꿔 쓰지 않는다.
- 미선택 299개를 강제 평가했을 때 105개가 `caution/anomaly`였다. 필요한 호출을 모두 보존했다거나 혼잡 이벤트 탐지 성능이 검증됐다고 주장하지 않는다.
- 객관적 혼잡 정답 라벨이 없으므로 선택·미선택 구간의 LLM 출력 분포 차이를 보고한 실험이다. 이를 정확도·재현율 같은 객관적 탐지 성능으로 표현하지 않는다.
- 트리거 정보가 LLM 판정에 영향을 줄 수 있다는 한계를 함께 명시한다.
- 논문 실험 설정은 Mall Dataset 2,000프레임, 1 fps 재구성, 5초 단위 400구간, YOLOv8m, OC-SORT, `gemini-3.1-flash-lite`, temperature 0이다. 현재 `config.py` 기본값이 바뀌어도 논문 실험 설정이 바뀐 것처럼 서술하지 않는다. 재현성을 주장할 때는 실제 실험 커밋·설정과 연결한다.

## 1. 패키지 위계 — perception/trigger/agent는 형제다

```
src/
├── perception/    LLM 없음, 상시 실행, trigger/LLM의 판단 정책을 모름
├── trigger/       규칙 기반 이벤트 게이트. LLM을 호출할지 결정
├── agent/         선택적 LLM 단발 판정 구현 (기존 패키지명; loop, prompt, schema, providers/, tools/)
├── io_utils/       영상 입출력 + 터미널 리포팅 + 세션 파일 관리(session.json/results.jsonl)
├── config.py       공용 설정 (세 레이어가 모두 참조)
├── datatypes.py     공용 dataclass (PerceptionResult, AggregatedFacts) + 노출 레지스트리(3절)
└── main.py          오케스트레이션 — 위 레이어를 조립하는 유일한 지점
```

`agent/`는 LLM 판정 구현 패키지일 뿐 시스템 전체나 상위 개념이 아니다. **perception/trigger를 `agent/` 밑에 다시 넣지 말 것.**
공용 모듈(`config.py`, `datatypes.py`)은 특정 레이어 소유로 두지 말고 `src/` 최상위에 둔다.

최상위 loose 모듈 이름은 표준 라이브러리와 겹치면 안 된다 (`datatypes.py`, `io_utils/`가 그 이유로 지어진 이름).

## 2. 파이프라인 흐름 (개요)

```
perception (모든 구간) → trigger (모든 구간) → LLM 단발 판정 (트리거 구간만)
```

- perception: 영상에서 관측값(`PerceptionResult`)을 계산해 방출
- trigger: 규칙 기반으로 LLM 호출 여부 결정 — 세부 계약은 `.claude/rules/trigger.md` 참고
- `agent/`: 트리거된 경우에만 텍스트 관측값으로 단발 판정 — 세부는 `.claude/rules/agent.md` 참고

**트리거 우선순위/재호출 계약이 명시돼 있지 않다.** `trigger/rules.py`는 네 조건을 모두 평가한 뒤 surge→stagnation→hotspot→conflict 순서로 대표 트리거 하나를 반환한다. 동시에 만족한 나머지는 `co_triggered`에 기록한다. cooldown/episode 상태가 없어서 같은 이상 상황이 여러 세그먼트 지속되면 매 세그먼트 LLM이 재호출된다. 이 동작을 바꾸려면 먼저 "트리거를 이벤트로 볼지 상태로 볼지"부터 정의할 것.

## 3. perception = observations, LLM = judgment

이 경계가 시스템 전체를 지탱한다. 위반하면 LLM이 도구를 우회해 직접 카운팅하는 문제(과거 시스템에서 실제로 발생: 가시 인원 ~15명인데 track 42개 보고)가 재발한다.

(과거엔 "tools = facts, LLM = judgment"를 슬로건으로 썼다. 설계 철학으로는 여전히 유효하지만, `agent/tools/`가 비어있는 상태에서 "tools"가 좁은 의미(`agent/tools/`)와 넓은 의미(perception 코드 포함)로 매번 갈려서 헷갈렸다. 지금 LLM 입력을 실제로 만드는 주체는 perception이므로 슬로건을 `perception = observations, LLM = judgment`로 바꿨다. 향후 tool-use가 복원되면 `perception computes observations, tools selectively expose evidence, LLM produces judgment`로 확장한다.)

- LLM은 **텍스트/숫자만** 입력받는다. 이미지·픽셀은 절대 LLM에 전달하지 않는다 (`agent/loop.py`의 `_facts_to_text`가 지금은 유일한 입력 경로 — tool-use 루프가 제거된 동안만 유효한 말이다. `TOOL_ONLY`가 채워져 tool 루프가 복원되면 tool 반환값도 입력 경로가 되므로, 그때 이 문장도 같이 갱신할 것). VLM을 쓰지 않는 이유가 이것이다 — 텍스트 전용 입력은 우회 가능성을 구조적으로 차단하는 장치지, 단순한 비용 절감이 아니다.
- LLM 출력 스키마(`agent/schema.py`의 `REQUIRED_FIELDS`)에는 `total_people` 같은 숫자 카운트 필드가 없다. 이런 필드는 **코드가 perception 관측값에서 직접 주입**한다 (`loop.py`의 `validated["total_people"] = facts.current.total`). `schema.validate()`는 LLM이 몰래 숫자 필드를 생산해도 `_FORBIDDEN_NUMERIC`으로 걷어낸다 — 이 방어를 제거하지 말 것. **단, 이 방어는 구조화 필드에만 적용된다.** `reasoning`은 자유 텍스트라 LLM이 그 안에 "약 30명이…" 같은 틀린 숫자를 재서술하는 것까지는 막지 못한다 — 알려진 한계로 남아있다.
- `tool_raw`는 (tool이 다시 생기면) 호출 원본을 그대로 보존한다 (연구용). 요약하거나 버리지 않는다.
- 새 tool을 추가할 때: `run(facts, **kwargs) -> dict`는 반드시 관측값만 반환해야 하고, 그 안에서 판단(assessment, action 등)을 생산하면 안 된다. 판단은 LLM의 몫이다.

### 노출 레지스트리 (`datatypes.py`)

`PerceptionResult`/`AggregatedFacts`의 각 필드를 LLM에게 어떤 경로로 보여줄지는 `datatypes.py`의 `ALWAYS_VISIBLE` / `TOOL_ONLY` / `NOT_EXPOSED` 세 집합이 유일하게 결정한다. 세 집합은 서로 배타적이며(assert로 강제), 필드마다 정확히 하나에만 속한다.

이전에는 이 판단이 `track_people` tool 안, `_facts_to_text` 안 등 코드 곳곳에 흩어져 즉흥적으로 결정되고 반복적으로 뒤집혔다. 새 perception 필드를 추가할 때는 반드시 이 레지스트리에 먼저 등록할 것 — `loop.py`나 tool 파일 안에서 개별적으로 노출 여부를 판단하지 말 것. `ALWAYS_VISIBLE`/`TOOL_ONLY` 분류 기준(매번 필요한 aggregate vs 가끔만 필요한 granular)은 이 레지스트리가 자동으로 답을 주지 않는다 — 여전히 사람 판단이 필요하다. `NOT_EXPOSED`는 애초에 판단 입력이 아닌 로깅/연구용 필드(`tracks`, `cv_elapsed_sec`, `timestamp`)다.

## 4. 향후 tool-use의 registry + interface 패턴

현재 `TOOL_ONLY`가 비어 있고 `agent/loop.py`의 tool-use 루프도 제거되어 있으므로 LLM은 외부 도구를 호출하지 않는다. 이는 논문의 “외부 도구를 호출하지 않는 선택적 LLM 단발 판정”과 일치한다.

향후 논문이 제시한 도구 선택 기능을 구현할 때는 tool-use 루프를 명시적으로 복원해야 한다. 그 기반이 복원된 뒤 새 도구는 기존 파일(`loop.py`, `agent/tools/__init__.py`)을 수정하지 않고 `agent/tools/`에 파일 하나만 추가하면 자동 등록되어야 한다.

```python
from . import register_tool

@register_tool(name="...", description="...", input_schema={...})
def my_tool(facts: AggregatedFacts, **kwargs) -> dict:
    ...
```

`agent/tools/__init__.py`는 `pkgutil.iter_modules`로 패키지 내 모든 모듈을 자동 import한다. tool-use 기반이 복원된 이후에는 새 파일과 `@register_tool`만으로 등록되게 하고, `loop.py`가 개별 도구 이름을 import하거나 if/elif로 분기하지 않게 한다. 현재 registry가 존재한다는 사실을 실제 tool-use가 구현된 것으로 서술하지 않는다.

### action 레이어 (향후 확장 — 현재 미구현)

tool(read, LLM 루프 안에서 호출)과 action(write, 판단 이후 부수효과 실행)은 성격이 반대이며 같은 레이어에 두지 않는다.

|           | tool                      | action                                          |
| --------- | ------------------------- | ----------------------------------------------- |
| 목적      | 사실을 가져옴 (read)      | 세상을 바꿈 (write)                             |
| 호출 시점 | LLM이 루프 중 호출        | 판단 _후_ dispatcher가 실행                     |
| 반환      | 사실(dict)                | 실행 결과 (부수효과)                            |
| 위치      | `agent/tools/` (agent 안) | `action/` (agent 밖, `src/` 최상위 형제 레이어) |

**지금 `action` 필드는 실행된 행동이 아니라 LLM이 생산한 대응 권고 수준이다.** `main.py`는 `agent_output`을 출력·저장만 하고 실제로 실행(dispatch)하지 않으며, `action/` 디렉토리는 아직 없다. 논문이 향후 과제로 제시한 상태 관리·도구 선택·후속 행동을 구현할 때에만 에이전트형 시스템이라는 분류를 재검토한다. 후속 행동이 필요해지면 `action/`을 `src/` 최상위 형제 레이어로 두고 LLM 판단과 부수효과 실행을 분리한다.

`session.json`/`results.jsonl` 기록(`io_utils/session.py`)은 action 예시가 아니다 — 이미 존재하는 관측성·재현성 인프라(pipeline infrastructure)이지, 판정 이후 실행되는 도메인 부수효과가 아니다. 둘을 같은 범주로 묶지 말 것.

### LLM 프로바이더도 같은 registry 패턴

`agent/providers/`는 tool과 같은 원칙(기존 파일 수정 없이 파일 하나 추가 + registry 등록)을 LLM 벤더 선택에 적용한 것이다. `config.AGENT_PROVIDER`(`"anthropic"` | `"gemini"`) 값으로 `agent/providers/__init__.py`의 `_PROVIDERS` dict에서 클래스를 고른다. 다만 tool과 달리 **상속 인터페이스가 아니라 duck-typing**이다 — `init_state`/`send`/`extract_text`/`extract_usage`/`is_retryable` 5개 메서드만 구현하면 되고, `agent/loop.py`는 어떤 프로바이더가 붙었는지 전혀 모른다. 새 프로바이더 추가 시 `agent/loop.py`를 건드리지 말 것 — 그 순간 이 패턴이 깨진다.

## 5. 패키징에 대한 현재 방침

지금은 `pyproject.toml`이 없다. 폴더 구조가 확정되지 않은 상태에서 패키징(entry point, 설치 방식)까지 같이 고민하면 결정할 게 늘어나기만 하므로 의도적으로 미룬 상태다. 실행은 `PYTHONPATH=src python src/main.py <video>` 방식으로 한다. 구조가 안정되면 `pyproject.toml`을 다시 추가하고, 그때 `datatypes.py`/`io_utils/` 같은 이름 충돌 회피가 여전히 유효한지 다시 점검한다.

## 6. 하지 말 것

- perception이 매 프레임 LLM을 호출하게 만들지 말 것 (latency, 비용, 그리고 "모든 프레임이 LLM을 거치는" 구조적 오류의 재발).
- LLM에게 이미지를 주지 말 것.
- tool의 `run()` 안에서 판단 필드를 생산하지 말 것.
- `schema.py`의 forbidden-field 방어를 우회하거나 제거하지 말 것.
- 트리거를 순간값 임계치 하나로 단순화하지 말 것 — 변화율/지속시간 기반을 유지할 것.
- action을 tool과 같은 디렉토리·같은 인터페이스로 섞지 말 것.
- perception/trigger를 `agent/` 밑으로 다시 넣지 말 것 (1절 위계 참고).
- 최상위 loose 모듈에 표준 라이브러리와 겹치는 이름을 쓰지 말 것.
- 현재 구현을 agent system/자율 에이전트/에이전틱 워크플로우라고 과장하지 말 것.
- 호출량 감소를 실제 비용·지연 감소나 혼잡 탐지 정확도 향상으로 바꿔 쓰지 말 것.
