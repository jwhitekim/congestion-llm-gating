# congestion-llm-gating

저장된 실내 영상을 세그먼트 단위로 순차 분석하고, 규칙 기반 혼잡 이벤트가 발생한 구간에서만 텍스트 LLM을 호출하는 training-free 워크플로우입니다. 기존 영상 기반 혼잡도 분석 구조를 규칙 기반 선택적 LLM 호출 방식으로 확장했습니다.

설계 원칙과 아키텍처 경계는 [.claude/CLAUDE.md](./.claude/CLAUDE.md)를 먼저 읽어야 합니다 — 이 문서는 설치/실행 방법과 현재 구현 상태를 다룹니다.

## 핵심 아이디어

이 시스템은 세 컴포넌트로 구성됩니다.

```
perception (모든 구간)  →  trigger (모든 구간)  →  LLM 단발 판정 (트리거 구간만)
YOLOv8m + OC-SORT             규칙 기반 이벤트 게이트       텍스트 관측값 기반
+ Line Density               (변화율·지속시간 기반)
```

- **perception = observations, LLM = judgment.** 사람 수, 밀도, 속도 등 관측값은 perception 코드가 계산하고, LLM은 그 관측값을 바탕으로 혼잡 상태와 대응 수준만 판정합니다. LLM은 카메라를 직접 보지 않습니다 — 모든 입력은 숫자/텍스트 관측값입니다.
- **LLM은 규칙이 선택한 구간에서만 호출되는 단발 판정 단계입니다.** 이상 이벤트(surge/stagnation/hotspot) 또는 규칙 간 상충 사례(conflict)가 감지될 때 구조화된 텍스트 관측값으로 한 번 호출되며, 실제 행동을 집행하지 않고 대응 권고 수준만 생산합니다.
- **perception/trigger/agent는 코드 소유권상 형제 패키지입니다.** 런타임은 `perception → trigger → LLM 단발 판정`의 단방향 흐름이며, `agent/`는 기존 LLM 판정 구현 패키지명입니다.

> 과거에는 "tools = facts, LLM = judgment"를 슬로건으로 썼습니다. 지금은 `agent/tools/`가 비어있고 관측값을 실제로 만드는 주체가 perception이라, 대표 슬로건을 `perception = observations, LLM = judgment`로 바꿨습니다. 설계 철학과 향후 tool 복원 시 확장 방향은 .claude/CLAUDE.md 3절을 참고하시기 바랍니다.

> 현재 구현의 논문 기준 명칭은 **규칙 기반 선택적 LLM 호출 워크플로우**입니다. `agent/`, `agent_output`, `AGENT_PROVIDER`의 `agent`는 기존 코드 식별자이며 현재 시스템을 자율 에이전트나 에이전틱 워크플로우로 분류한다는 뜻이 아닙니다. 상태 관리·도구 선택·후속 행동을 포함하는 에이전트형 시스템은 향후 확장 범위입니다.

## 설치

```bash
pip install -r requirements.txt
make install   # dashboard/ npm 의존성 설치
```

`requirements.txt`는 CUDA 12.6 GPU 빌드 `torch`/`torchvision`과 `ultralytics`(YOLOv8), `ocsort`를 설치합니다. GPU 환경(CUDA)을 권장합니다. YOLO 모델은 `config.YOLO_MODEL_CHOICE`에 따라 COCO 사전학습 `yolov8m.pt` 또는 `models/`의 fine-tuned 가중치를 사용합니다. `make install`은 `npm --prefix dashboard install`만 실행하고 Python 의존성 설치는 안내만 합니다 — GPU 빌드 선택이 걸린 설치라 자동으로 실행하지 않습니다.

LLM 판정에는 `ANTHROPIC_API_KEY` 환경변수가 필요합니다(`anthropic` SDK, 기본 모델: `claude-sonnet-4-6`, `ANTHROPIC_MODEL`로 override 가능). 실험적으로 Gemini도 지원합니다 — `AGENT_PROVIDER=gemini`로 설정하면 `google-genai` SDK로 기본 `gemini-3.5-flash`(`GEMINI_MODEL`로 override 가능, `GEMINI_API_KEY` 필요)를 대신 호출합니다. 두 프로바이더 모두 `agent/providers/`의 duck-typing 인터페이스(`init_state/send/extract_text/extract_usage/is_retryable`)만 구현하면 되므로, 새 프로바이더를 추가해도 `agent/loop.py`는 건드릴 필요가 없습니다.

API 호출은 네트워크/rate limit/서버 오류에 한해 지수 백오프로 자동 재시도합니다(`config.AGENT_MAX_RETRIES`, 기본 3회). LLM 판단 자체의 재시도(self-correction)와는 무관합니다.

## 실행

```bash
make run                                  # videos/department_store.mp4 (기본값)
make run VIDEO=videos/supermarket.mp4     # 다른 영상 지정
```

`make run`은 `PYTHONPATH=src python src/main.py $(VIDEO)`를 실행합니다 — 패키지 설치 없이 `src/`를 `PYTHONPATH`에 직접 넣는 구조라 `make` 없이도 그 명령을 직접 실행하면 동일하게 동작합니다.

실행마다 `outputs/<timestamp>/` 세션 폴더가 새로 생성됩니다. `session.json`은 세션 메타데이터(시작/종료 시각, config snapshot)를, `results.jsonl`은 세그먼트별 결과를 한 줄씩 즉시 기록합니다 — 트리거되지 않은 세그먼트도 기존 스키마 필드인 `agent: null`로 포함하고, 트리거가 발생했다면 `trigger_reason`도 함께 남깁니다. 현재 선택적 호출 프롬프트에는 트리거 이름과 정량적 근거가 포함되며, 이 정보가 LLM 판정에 영향을 줄 수 있다는 점은 논문의 한계입니다. `scripts/ab_trigger_reason.py`는 그중 정량적 `trigger_reason` 문장 유무만 비교하며 트리거 프라이밍 전체를 제거하는 실험은 아닙니다.

결과 시각화 대시보드는 [`dashboard/`](./dashboard)를 참고하시기 바랍니다.

```bash
make dash         # 개발 서버 (npm --prefix dashboard run dev)
make dash-build   # 정적 빌드 (npm --prefix dashboard run build)
```

대시보드는 폴더 선택/드래그앤드롭이 없습니다 — Vite dev 서버의 미들웨어(`vite.config.js`)가 고정 루트 `outputs/`(`io_utils/session.py`의 `OUTPUTS_DIR`)를 직접 읽어 `/api/sessions*`로 내려주고, 브라우저는 그걸 fetch만 합니다. 브라우저 파일시스템 권한이 필요 없어 VS Code Simple Browser 같은 제한적 webview에서도 동일하게 동작합니다. 세션이 아직 실행 중이면 1초 간격으로 자동 갱신합니다. **`make dash-build`로 만든 정적 빌드에는 이 API가 없습니다** — `configureServer`는 dev 서버 전용이라 `vite preview`나 정적 배포에서는 세션 목록이 뜨지 않습니다.

## 디렉토리 구조

```
src/
├── main.py                 워크플로우 오케스트레이션 (perception→trigger→LLM 판정)
├── config.py                공용 설정 — 모든 임계값·모델 경로·존 정의·AGENT_PROVIDER
├── datatypes.py               공용 dataclass(PerceptionResult, AggregatedFacts) +
│                                ALWAYS_VISIBLE/TOOL_ONLY/NOT_EXPOSED 노출 레지스트리
├── perception/               perception 컴포넌트 (LLM 없음, 상시 실행)
│   ├── detector.py              YOLO 추론
│   ├── tracker.py                OC-SORT 래퍼 (`use_byte=True`)
│   ├── density.py                 Line Density, 평균 속도 계산
│   ├── zone_metrics.py             구역별 정규화 밀도 + 집중도(HHI) 계산
│   └── pipeline.py                 프레임 스트림 → PerceptionResult 스트림
├── trigger/                  trigger 컴포넌트 (rule 기반 게이팅)
│   ├── history.py               SegmentHistory 링버퍼 (변화율/추세 기준값)
│   └── rules.py                   트리거 판정 (surge/stagnation/hotspot/conflict)
├── agent/                    선택적 LLM 단발 판정 (기존 패키지명, tool 없음)
│   ├── loop.py                    호출 오케스트레이션 + 재시도 + facts→텍스트 변환
│   ├── prompt.py                   system prompt
│   ├── schema.py                    LLM 출력 검증 + 금지 필드(숫자 카운트) 제거
│   ├── providers/                    프로바이더 registry (anthropic/gemini, duck-typing)
│   └── tools/                        현재 비어있음 — 향후 tool-use 기반 복원 시 사용
└── io_utils/
    ├── sampler.py                  영상 → 프레임 스트림
    ├── reporter.py                  터미널 출력 (rich)
    └── session.py                    outputs/<timestamp>/ 세션 폴더, session.json/results.jsonl 관리

scripts/
├── analyze_bottleneck.py     results.jsonl에서 LLM 호출 왕복시간/토큰 상관관계 분석
└── probe_agent.py              합성 case로 LLM 출력이 입력에 따라 실제로 차별화되는지 확인
```

perception, trigger, agent, io_utils는 `src/` 밑에 형제로 위치하며 어느 것도 다른 것 밑에 종속되지 않습니다 — 이 위계가 필요한 이유는 .claude/CLAUDE.md 1절을 참고하시기 바랍니다. `agent/` 폴더는 시스템 전체가 아니라 선택적 LLM 판정 구현만 담습니다.

`agent/tools/`는 지금 비어있습니다. `track_people` tool이 있었으나 `_facts_to_text`가 넘기는 정보와 완전히 중복돼(no-op) 삭제했습니다. 어떤 필드를 LLM에게 어떤 경로로 보여줄지는 `datatypes.py`의 노출 레지스트리 한 곳에서만 결정합니다. 향후 `TOOL_ONLY`가 채워지면 provider와 `agent/loop.py`의 tool-use 기반도 함께 복원해야 하며, 현재 registry만으로 LLM이 도구를 호출하지는 않습니다.

## 트리거 조건 (`config.py`)

| 트리거     | 조건                                                                                          |
| ---------- | --------------------------------------------------------------------------------------------- |
| surge      | density가 직전 이동평균의 `SURGE_RATIO`(1.4)배 초과                                           |
| stagnation | 평균 속도가 `SPEED_MIN`(0.5px/s) 미만으로 `STAG_SEC`(10초) 이상 지속                          |
| hotspot    | 한 구역 인원이 percentile 기반 `zone_max` 초과(콜드스타트는 `ZONE_MAX=8`)                     |
| conflict   | 순간값 기준 `level=low`인데 `density_slope`가 `CONFLICT_SLOPE_MIN`(0.4) 초과 — 순간값과 추세 판정이 상충하는 경계 사례 |

surge/stagnation은 변화율 또는 지속시간 기준입니다. conflict는 "규칙 두 개가 서로 다른 결론을 낸다"는 것 자체가 트리거 조건입니다 — surge는 직전 평균 대비 비율이라 완만하지만 꾸준한 상승은 못 잡고, level은 순간 density만 보므로 추세를 모릅니다. 이 경계 사례를 LLM에 넘겨 해석하게 하는 것이 conflict의 존재 이유입니다(`trigger/rules.py` 4번 조건 주석 참고).

**hotspot은 이 원칙의 유일한 예외입니다.** 다른 세 트리거와 달리 `zone_count > zone_max` 순간값만 보고 즉시 발동하며 지속시간 조건이 없습니다. `zone_max`는 표본 20개 이후 최근 구역 인원 분포의 90 percentile을 사용하고, 콜드스타트에는 고정값 8을 사용합니다. 의도적 예외로 남길지 지속시간 조건을 추가할지는 미결정입니다.

**`density_slope`/`speed_trend`는 초당이 아니라 세그먼트당 선형회귀 기울기입니다**(`trigger/history.py`, x축이 시간이 아니라 세그먼트 인덱스). `CONFLICT_SLOPE_MIN=0.4`의 의미는 `SEGMENT_INTERVAL`(현재 5초)에 종속적이므로, `SEGMENT_INTERVAL`을 바꾸면 `CONFLICT_SLOPE_MIN`도 재보정해야 합니다.

**트리거 우선순위와 반복 호출 계약이 명시돼 있지 않습니다.** `trigger/rules.py`는 네 조건을 모두 평가한 뒤 surge→stagnation→hotspot→conflict 순서로 대표 트리거 하나를 반환하고, 나머지는 `co_triggered`에 기록합니다. cooldown이 없어서 같은 이상 상황이 여러 세그먼트 지속되면 매 세그먼트 LLM을 다시 호출합니다. 논문의 호출량 감소는 이 현재 동작에서 측정된 결과이며 이벤트당 1회 호출을 뜻하지 않습니다.

## 현재 상태 / 미구현

- **기본 검출기가 COCO 전신 모델로 바뀌었습니다.** `config.YOLO_MODEL_CHOICE`(기본값 `"base"`)가 `YOLO_BASE_MODEL_NAME`(`yolov8m.pt`, COCO 사전학습 전신 검출)을 기본으로 로드합니다. 기존 capdi(`YOLO_FINE_TUNED_MODEL_NAME`, head 검출기)는 `YOLO_MODEL_CHOICE=fine_tuned`로 여전히 선택할 수 있습니다. 검출기가 head→전신으로 바뀌며 density 스케일이 달라졌습니다(약 0~140 → 0~350대, `config.py` 주석 참고) — 아래 percentile 기반 동적 임계값이 이 변화에 대한 대응입니다.
- **OC-SORT가 `use_byte=True`로 동작합니다.** 트래커는 conf 0.3 이상 detection으로만 새 트랙을 시작하지만, conf 0.1~0.3 구간은 기존 트랙과의 2차(BYTE) 매칭에 쓰입니다 — conf 0.1 이하만 완전히 버려집니다. `src/perception/tracker.py` 주석을 참고하시기 바랍니다.
- **density/zone 임계값이 percentile 기반 동적값으로 바뀌었습니다.** `trigger/history.py`의 `ThresholdHistory`가 최근 `PERCENTILE_HISTORY_MAXLEN`(기본 100세그먼트) 구간의 density/zone 분포에서 `DENSITY_LOW/HIGH_PERCENTILE`, `ZONE_MAX_PERCENTILE` 퍼센타일을 계산합니다. 표본이 `MIN_SAMPLES_FOR_PERCENTILE`(기본 20) 미만인 콜드스타트 구간에서는 기존 고정값(`DENSITY_LOW/HIGH`, `ZONE_MAX`)으로 fallback합니다. 어느 쪽이 쓰였는지는 `results.jsonl`의 `dynamic_thresholds.source`(`"fallback"`|`"percentile"`)에 세그먼트마다 기록됩니다.
- **action 레이어가 없습니다.** `action` 필드는 실행된 행동이 아니라 LLM이 생산한 대응 권고 수준이며, 현재는 판정 결과를 출력·저장만 합니다. 상태 관리·도구 선택·후속 행동을 포함하는 에이전트형 시스템은 논문이 제시한 향후 확장입니다.
- **연구 기여는 LLM 호출 시점의 선택입니다.** 논문은 규칙 기반 게이팅을 단순 구현 세부가 아니라 독립적인 시스템 설계 문제로 다룹니다. 다만 객관적 혼잡 정답 라벨이 없으므로 혼잡 탐지 성능을 검증한 것으로 확대 해석하지 않습니다.
- **hotspot 순간값 문제, 트리거 우선순위/반복 호출 계약 부재** — 상세는 위 "트리거 조건" 절을 참고하시기 바랍니다. 둘 다 결정만 남았습니다.
- **Gemini 프로바이더는 실험적 상태입니다.** Sonnet/Haiku 레이턴시 비교 목적으로 추가했고, 정식 지원 대상인지는 미결정입니다.
- **`reasoning` 필드의 숫자 hallucination은 스키마 방어 범위 밖입니다.** `schema.py`가 `total_people` 같은 구조화 필드는 걸러내지만, LLM이 자유 텍스트 `reasoning`에 "약 30명이…" 같은 틀린 숫자를 재서술하는 것은 막지 못합니다. 알려진 한계로 남아있습니다.
