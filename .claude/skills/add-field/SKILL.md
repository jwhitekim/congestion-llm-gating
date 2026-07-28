---
name: add-field
description: 새 perception 필드나 tool을 추가할 때 datatypes.py의 노출 레지스트리(ALWAYS_VISIBLE/TOOL_ONLY/NOT_EXPOSED) 등록 체크리스트를 안내한다. perception/pipeline.py나 agent/tools/에 새 필드·tool을 추가하려 할 때 사용한다.
---

# 필드/tool 추가 체크리스트

1. `datatypes.py`의 `ALWAYS_VISIBLE`/`TOOL_ONLY`/`NOT_EXPOSED` 중 어디에 등록할지 먼저 결정한다
   - 매 세그먼트 필요한 aggregate → `ALWAYS_VISIBLE`
   - 가끔만 필요한 granular 값 → `TOOL_ONLY`
   - 로깅/연구 전용 → `NOT_EXPOSED`
2. 세 집합이 서로 배타적인지(assert 통과하는지) 확인한다
3. dataclass의 새 필드가 정확히 한 집합에 포함됐는지 수동으로 확인한다
4. `loop.py`에서 노출 여부를 따로 판단하는 코드가 생기지 않았는지 확인한다
5. `agent/tools/`의 registry만으로는 tool-use가 동작하지 않음을 확인한다. 도구 선택을 구현하려면 provider와 `agent/loop.py`의 실행 경로를 함께 다룬다

등록 위치가 애매하면 임의로 정해서 진행하지 말고 먼저 물어본다.
