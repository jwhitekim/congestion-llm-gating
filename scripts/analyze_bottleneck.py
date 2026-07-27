"""
선택적 LLM 호출 병목 분석 스크립트.

results.jsonl에서 LLM이 호출된 세그먼트(entry["agent"] is not None)만 추려
api_call_breakdown 필드를 바탕으로:
  - 왕복 1회당 평균 소요 시간
  - 왕복 횟수 분포 (1회/2회/3회 이상)
  - output_tokens와 왕복 시간의 상관관계 (피어슨 r)
  - duplicate_tool_calls 비율
를 계산해 터미널에 출력한다.

사용법: PYTHONPATH=src python scripts/analyze_bottleneck.py <results.jsonl>
(경로 생략 시 outputs/ 아래 가장 최근 세션의 results.jsonl을 사용)
"""

import json
import sys
from pathlib import Path
from statistics import mean, pstdev


def _latest_results_file() -> Path:
    outputs_dir = Path("outputs")
    sessions = sorted(outputs_dir.iterdir(), key=lambda p: p.name)
    if not sessions:
        raise FileNotFoundError("outputs/ 아래 세션이 없습니다.")
    return sessions[-1] / "results.jsonl"


def _pearson_r(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2:
        return None
    mx, my = mean(xs), mean(ys)
    sx, sy = pstdev(xs), pstdev(ys)
    if sx == 0 or sy == 0:
        return None
    cov = mean((x - mx) * (y - my) for x, y in zip(xs, ys))
    return cov / (sx * sy)


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else _latest_results_file()
    print(f"분석 대상: {path}\n")

    agent_segments = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            entry = json.loads(line)
            if entry.get("agent") is not None:
                agent_segments.append(entry)

    if not agent_segments:
        print("LLM이 호출된 세그먼트가 없습니다 (트리거 미발생).")
        return

    print(f"LLM 호출 세그먼트 수: {len(agent_segments)}\n")

    all_round_trips: list[dict] = []
    round_trip_counts: list[int] = []
    duplicate_flags: list[bool] = []

    for entry in agent_segments:
        agent = entry["agent"]
        breakdown = agent.get("api_call_breakdown", [])
        all_round_trips.extend(breakdown)
        round_trip_counts.append(len(breakdown))
        duplicate_flags.append(bool(agent.get("duplicate_tool_calls", False)))

    # --- 왕복 1회당 평균 소요 시간 ---
    elapsed_list = [c["elapsed_sec"] for c in all_round_trips]
    print("=== 왕복(API round-trip)별 소요 시간 ===")
    print(f"  총 왕복 횟수: {len(elapsed_list)}")
    print(f"  평균: {mean(elapsed_list):.3f}초")
    if len(elapsed_list) > 1:
        print(f"  표준편차: {pstdev(elapsed_list):.3f}초")
    print(f"  최소/최대: {min(elapsed_list):.3f}초 / {max(elapsed_list):.3f}초\n")

    # --- 세그먼트당 왕복 횟수 분포 ---
    print("=== 세그먼트당 왕복 횟수 분포 ===")
    bucket_1 = sum(1 for c in round_trip_counts if c == 1)
    bucket_2 = sum(1 for c in round_trip_counts if c == 2)
    bucket_3plus = sum(1 for c in round_trip_counts if c >= 3)
    total = len(round_trip_counts)
    print(f"  1회: {bucket_1} ({bucket_1/total:.0%})")
    print(f"  2회: {bucket_2} ({bucket_2/total:.0%})")
    print(f"  3회 이상: {bucket_3plus} ({bucket_3plus/total:.0%})\n")

    # --- output_tokens vs 왕복 시간 상관관계 ---
    output_tokens = [c["output_tokens"] for c in all_round_trips if c.get("output_tokens") is not None]
    matched_elapsed = [c["elapsed_sec"] for c in all_round_trips if c.get("output_tokens") is not None]
    r = _pearson_r(matched_elapsed, output_tokens)
    print("=== output_tokens vs 왕복 시간 상관관계 ===")
    if r is None:
        print("  계산 불가 (데이터 부족 또는 분산 0)")
    else:
        print(f"  피어슨 상관계수 r = {r:.3f}")
        if abs(r) >= 0.6:
            print("  → 강한 상관관계: 추론(reasoning) 시간이 왕복 시간을 지배 (병목 B)")
        elif abs(r) >= 0.3:
            print("  → 약한/중간 상관관계: 추론과 네트워크/큐잉이 혼합된 병목")
        else:
            print("  → 상관관계 거의 없음: 네트워크/큐잉 지연이 병목일 가능성 (병목 A)")
    print()

    # --- duplicate_tool_calls 비율 ---
    dup_count = sum(duplicate_flags)
    print("=== 중복 도구 호출(duplicate_tool_calls) 비율 ===")
    print(f"  {dup_count}/{total} ({dup_count/total:.0%}) 세그먼트에서 중복 발생\n")

    # --- 종합 판정 ---
    print("=== 종합 ===")
    print(f"  평균 왕복 시간: {mean(elapsed_list):.3f}초 x 평균 왕복 횟수: {mean(round_trip_counts):.2f}회")
    print(f"  ≈ LLM 호출당 평균 API 시간: {mean(elapsed_list) * mean(round_trip_counts):.3f}초")


if __name__ == "__main__":
    main()
