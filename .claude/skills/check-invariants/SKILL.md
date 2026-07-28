---
name: check-invariants
description: 코드 변경이 perception=observations/LLM=judgment 경계, never-images, no-numeric-LLM-output 같은 핵심 아키텍처 불변조건을 위반하는지 점검한다. datatypes.py, schema.py, agent/loop.py, perception/, trigger/rules.py를 수정하거나 새 perception 필드/트리거를 추가한 후에 사용한다.
---

# 불변조건 점검

방금 수정한 파일들이 `.claude/CLAUDE.md`의 핵심 원칙(perception = observations, LLM = judgment)을 위반하지 않는지 확인한다.

## 점검 항목

1. LLM에 이미지/픽셀이 전달되는 경로가 새로 생겼는지 (`agent/loop.py`, `agent/providers/`)
2. `agent/schema.py`의 `REQUIRED_FIELDS`에 숫자 카운트 필드가 추가됐는지 — 숫자는 코드가 주입해야 한다
3. 새 perception 필드가 `datatypes.py`의 `ALWAYS_VISIBLE`/`TOOL_ONLY`/`NOT_EXPOSED` 중 정확히 한 곳에 등록됐는지. 현재 assert는 누락을 검사하지 않는다
4. `trigger/rules.py`에 새 트리거를 추가했다면 순간값이 아니라 변화율·지속시간 기반인지 (hotspot은 의도적 예외, 새 코드가 이 패턴을 그대로 따라가지 않도록 주의)

## 출력 형식

위반이 있으면 파일:라인과 함께 지적. 없으면 "위반 없음"이라고만 짧게 답한다. 근거 없이 구조를 부풀리지 않는다.
