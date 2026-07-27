---
paths:
  - "src/trigger/**/*"
---

# trigger 레이어 세부 계약

`trigger/rules.py`는 매 세그먼트 `PerceptionResult` + `SegmentHistory`를 받아 rule로 트리거 여부를 판정한다.

**순간값이 아니라 변화율·지속시간 기반**이어야 한다(`density_delta_ratio`, `low_speed_streak_sec` 등) — 새 트리거 추가 시에도 이 기준을 지킬 것. **`hotspot`이 이 원칙의 유일한 예외**다(`zone_count > zone_max` 순간값만 보고 즉시 발동하며, `zone_max`는 percentile 기반이고 콜드스타트에는 `ZONE_MAX`를 사용) — 새 코드가 이 패턴을 따라가지 않도록 주의. 의도적 예외로 유지할지 지속시간 조건을 추가할지는 미결정. `conflict` 트리거(`density_slope` 기반)는 원칙을 지킨다.

**우선순위/재호출 계약이 명시돼 있지 않다.** 네 조건을 모두 독립적으로 평가한 뒤 surge→stagnation→hotspot→conflict 순서로 대표 `trigger_name` 하나를 반환한다(우선순위는 코드 순서가 암묵적으로 정함). cooldown/episode 상태가 없어서 같은 이상 상황이 지속되면 매 세그먼트 LLM이 재호출된다. 이 동작을 바꾸려면 먼저 "트리거를 이벤트로 볼지 상태로 볼지"부터 정의할 것 — 새 트리거를 추가하며 이 계약을 암묵적으로 더 복잡하게 만들지 말 것.

`evaluate()`는 4개 조건을 전부 독립적으로 판정하고, `trigger_name`으로 뽑히지 않았지만 같은 세그먼트에서 동시에 만족된 다른 트리거 이름들은 `co_triggered`(list[str])에 담아 `results.jsonl`에만 기록한다 — LLM 호출·프롬프트·판정 로직에는 전혀 영향을 주지 않는 순수 기록용 필드다(실측: t=15에서 surge가 `trigger_name`, hotspot은 `co_triggered=["hotspot"]`로 함께 기록됨).

**`conflict`는 `current.total > 0` 가드를 반드시 통과해야 한다** — `density_slope_with()`가 HISTORY_WINDOW(30초, 6세그먼트+현재=7포인트) 전체 선형회귀라 "스파이크 후 원래대로 복귀"한 구간도 회귀선상 양수 기울기로 잡히고, 그 시점의 `total`이 0이면 판정 대상 자체가 없어 오탐이 된다(실측: department_store.mp4 t=280, density=0.0인데 직전 윈도우 slope=2.4872로 발동, LLM이 매번 "노이즈"로 판정하면서도 API 호출은 이미 발생).
