"""
trigger_reason 프롬프트 주입 효과 A/B 비교.

배경: 선택적 LLM 판정 함수인 agent/loop.py의 run()은 트리거 발생 시
"트리거 발생: {trigger_name} ({trigger_reason})"
형태로 trigger_reason(예: "density 28.0 > avg 17.5 × 1.4 (ratio=1.60)")을 프롬프트에 넣는다.
이 문장은 이미 _facts_to_text()가 보여주는 raw 수치(density, density_delta_ratio,
zone_counts 등)에서 유도 가능한 결론을 자연어로 미리 요약해 준 것 — 즉 "새 정보"가 아니라
"이미 보여준 수치의 재서술"이다. 이 스크립트는 그 재서술 유무에 따라 LLM 출력의
일관성과 사전에 정한 기대 방향 일치율이 달라지는지 비교한다. 객관적 혼잡
정답 라벨을 이용한 판단 품질 검증은 아니다.

이 비교는 trigger_reason 문장 유무만 다룬다. trigger_name과 "트리거가 이미 이상
신호를 감지했다"는 system prompt는 두 조건에 공통이므로, 트리거 정보 전체의
프라이밍 효과를 제거하거나 측정하는 실험은 아니다.

- A (no_reason): include_trigger_reason=False — trigger_name만, reason 문장 제외
- B (with_reason): include_trigger_reason=True — 기존 기본 동작

probe_agent.py의 5개 합성 시나리오(PROBES)를 그대로 재사용한다 — 각 시나리오는 이미
"기대 방향"이 주석으로 문서화돼 있어 soft pass/fail 채점 기준으로 쓸 수 있다.
같은 조건을 REPEATS회 반복해 (1) 조건별 판정 일관성, (2) 기대 방향 일치율을 측정한다.

실제 LLM API를 호출한다 (비용 발생). 기본 REPEATS=3 x probe 5개 x 조건 2개 = 30회 호출.

사용법: PYTHONPATH=src python scripts/ab_trigger_reason.py [출력저장경로.json]
"""

import json
import sys
from collections import Counter

import config
from agent import loop as agent_loop
from probe_agent import PROBES

REPEATS = 3

_ASSESSMENT_ORDER = {"normal": 0, "caution": 1, "anomaly": 2}
_ACTION_ORDER = {"none": 0, "monitor": 1, "alert": 2}

# PROBES 주석의 "기대 방향"을 순서형 임계값으로 인코딩한 것 — 강제 사양이 아니라
# soft pass/fail 채점 기준. min/max/exact 중 명시된 것만 검사.
_EXPECTATIONS = {
    "probe_stable": {"assessment_max": 1, "action_max": 1},
    "surge": {"assessment_min": 1, "action_min": 1},
    "hotspot": {"assessment_min": 1, "action_min": 1},
    "stagnation": {"assessment_min": 1},
    "conflict": {"action_exact": 1},
}


def _passes_expectation(trigger_name: str, assessment: str, action: str) -> bool | None:
    exp = _EXPECTATIONS.get(trigger_name)
    if exp is None:
        return None
    a = _ASSESSMENT_ORDER.get(assessment)
    act = _ACTION_ORDER.get(action)
    if a is None or act is None:
        return False
    if "assessment_min" in exp and a < exp["assessment_min"]:
        return False
    if "assessment_max" in exp and a > exp["assessment_max"]:
        return False
    if "action_min" in exp and act < exp["action_min"]:
        return False
    if "action_max" in exp and act > exp["action_max"]:
        return False
    if "action_exact" in exp and act != exp["action_exact"]:
        return False
    return True


def _run_condition(trigger_name, trigger_reason, facts, include_reason: bool) -> list[dict]:
    runs = []
    for _ in range(REPEATS):
        output = agent_loop.run(
            facts, trigger_name, trigger_reason, config.ZONE_MAX, include_trigger_reason=include_reason
        )
        runs.append(
            {
                "assessment": output.get("assessment"),
                "action": output.get("action"),
                "distribution_summary": output.get("distribution_summary"),
                "reasoning": output.get("reasoning"),
            }
        )
    return runs


def _summarize(runs: list[dict], trigger_name: str) -> dict:
    assessments = Counter(r["assessment"] for r in runs)
    actions = Counter(r["action"] for r in runs)
    passes = [_passes_expectation(trigger_name, r["assessment"], r["action"]) for r in runs]
    passes = [p for p in passes if p is not None]
    return {
        "assessment_counts": dict(assessments),
        "action_counts": dict(actions),
        "assessment_consistency": assessments.most_common(1)[0][1] / len(runs),
        "action_consistency": actions.most_common(1)[0][1] / len(runs),
        "expectation_pass_rate": (sum(passes) / len(passes)) if passes else None,
    }


def main() -> None:
    all_results = {}
    print(f"REPEATS={REPEATS} (조건당), probe {len(PROBES)}개, 총 API 호출 {REPEATS * len(PROBES) * 2}회\n")

    for trigger_name, trigger_reason, facts in PROBES:
        print(f"=== {trigger_name} ===")
        print(f"  trigger_reason: {trigger_reason}")

        runs_a = _run_condition(trigger_name, trigger_reason, facts, include_reason=False)
        runs_b = _run_condition(trigger_name, trigger_reason, facts, include_reason=True)

        summary_a = _summarize(runs_a, trigger_name)
        summary_b = _summarize(runs_b, trigger_name)

        print(f"  [A: no_reason]   assessment={summary_a['assessment_counts']} "
              f"action={summary_a['action_counts']} "
              f"consistency=({summary_a['assessment_consistency']:.2f}/{summary_a['action_consistency']:.2f}) "
              f"기대일치율={summary_a['expectation_pass_rate']}")
        print(f"  [B: with_reason] assessment={summary_b['assessment_counts']} "
              f"action={summary_b['action_counts']} "
              f"consistency=({summary_b['assessment_consistency']:.2f}/{summary_b['action_consistency']:.2f}) "
              f"기대일치율={summary_b['expectation_pass_rate']}")
        print()

        all_results[trigger_name] = {
            "trigger_reason": trigger_reason,
            "A_no_reason": {"runs": runs_a, "summary": summary_a},
            "B_with_reason": {"runs": runs_b, "summary": summary_b},
        }

    if len(sys.argv) > 1:
        with open(sys.argv[1], "w", encoding="utf-8") as f:
            json.dump(all_results, f, ensure_ascii=False, indent=2)
        print(f"저장: {sys.argv[1]}")


if __name__ == "__main__":
    main()
