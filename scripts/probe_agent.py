"""
합성 probe case로 LLM 판정이 입력(crowd size/zone 분포)에 따라 실제로
차별화되는지 확인하는 스크립트. PerceptionPipeline/trigger를 거치지 않고
AggregatedFacts를 직접 구성해 선택적 판정 함수인 agent_loop.run()을 호출한다.

실제 LLM API를 호출한다(기본 5개 세그먼트 판정). 각 판정은 single-shot이지만
일시적인 API 실패에는 전송 재시도가 발생할 수 있다.

사용법: PYTHONPATH=src python scripts/probe_agent.py [출력저장경로.json]
"""

import json
import sys

import config
from datatypes import PerceptionResult, AggregatedFacts
from perception.zone_metrics import calc_zone_density, calc_concentration
from agent import loop as agent_loop


def _facts(total, density, avg_speed, zone_counts, delta_ratio, speed_trend, density_slope, level):
    zone_density = calc_zone_density(zone_counts, config.ZONES)
    concentration = calc_concentration(zone_counts)
    current = PerceptionResult(
        timestamp=0.0,
        total=total,
        density=density,
        avg_speed=avg_speed,
        zone_counts=zone_counts,
        zone_density=zone_density,
        concentration=concentration,
        tracks=[],
        cv_elapsed_sec=0.0,
    )
    return AggregatedFacts(
        current=current,
        density_delta_ratio=delta_ratio,
        speed_trend=speed_trend,
        density_slope=density_slope,
        level=level,
    )


# (trigger_name, trigger_reason, facts) — 서로 다른 crowd size/zone 분포/추세를 갖는 5개 시나리오.
# trigger_reason은 trigger/rules.py의 실제 발동 조건(config.py 임계값 기준)을 모방해
# 합성한 문자열이다 — probe는 PerceptionPipeline/rules.evaluate()를 거치지 않으므로
# rules.py가 실제로 이 값을 산출하는 것은 아니다.
# 기대 방향(참고용, 강제 검증 대상 아님):
#   probe_stable   : 전반적으로 안정 → normal/none 방향
#   surge          : 균등 분포의 전역 급증 → caution/monitor 방향
#   hotspot        : 한 구역에 극단적으로 쏠린 국소 밀집 → 더 강한 경보 방향
#   stagnation     : 밀도는 중간이지만 정체 지속 → caution 이상
#   conflict       : 순간값은 낮지만 추세가 가파름 → 조기 경보(monitor)이되 alert는 아님
PROBES = [
    ("probe_stable", "density 4.0 ~ avg 3.9 (ratio=1.02) — 임계 미도달, 정상 범위",
     _facts(4, 4.0, 35.0, {"A": 2, "B": 1, "C": 1}, 1.02, 0.01, 0.02, "low")),
    ("surge", "density 28.0 > avg 17.5 × 1.4 (ratio=1.60)",
     _facts(28, 28.0, 20.0, {"A": 9, "B": 10, "C": 9}, 1.6, -0.05, 0.3, "medium")),
    ("hotspot", "hotspot: A구역 32명 > 임계 8",
     _facts(37, 20.0, 15.0, {"A": 32, "B": 3, "C": 2}, 1.1, -0.02, 0.1, "medium")),
    ("stagnation", "avg_speed 0.20 px/s < 0.5 for 15s",
     _facts(18, 18.0, 0.2, {"A": 6, "B": 6, "C": 6}, 1.05, -0.15, 0.05, "medium")),
    ("conflict", "conflict: level=low이지만 density_slope=0.90 > 임계 0.4 — 순간값과 추세 판정이 상충",
     _facts(12, 12.0, 25.0, {"A": 4, "B": 4, "C": 4}, 1.15, -0.03, 0.9, "low")),
]


def main() -> None:
    results = []
    for trigger_name, trigger_reason, facts in PROBES:
        output = agent_loop.run(facts, trigger_name, trigger_reason, config.ZONE_MAX)
        output_tokens_total = sum(
            c["output_tokens"] for c in output["api_call_breakdown"] if c.get("output_tokens") is not None
        )
        row = {
            "trigger": trigger_name,
            "assessment": output.get("assessment"),
            "action": output.get("action"),
            "congestion_level": output.get("congestion_level"),
            "local_hotspots": output.get("local_hotspots"),
            "distribution_summary": output.get("distribution_summary"),
            "reasoning": output.get("reasoning"),
            "recorded_api_responses": len(output["api_call_breakdown"]),
            "output_tokens_per_response": [c.get("output_tokens") for c in output["api_call_breakdown"]],
            "output_tokens_total": output_tokens_total,
        }
        results.append(row)
        print(
            f"[{trigger_name:12s}] assessment={row['assessment']:8s} action={row['action']:8s} "
            f"level={row['congestion_level']:6s} tokens={row['output_tokens_total']:4d} "
            f"hotspots={row['local_hotspots']}"
        )

    distinct_assessment = {r["assessment"] for r in results}
    distinct_action = {r["action"] for r in results}
    print(f"\n서로 다른 assessment 값 수: {len(distinct_assessment)} {distinct_assessment}")
    print(f"서로 다른 action 값 수: {len(distinct_action)} {distinct_action}")

    if len(sys.argv) > 1:
        with open(sys.argv[1], "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"저장: {sys.argv[1]}")


if __name__ == "__main__":
    main()
