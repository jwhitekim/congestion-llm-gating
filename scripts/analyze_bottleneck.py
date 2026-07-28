"""
선택적 LLM 호출 병목 분석 스크립트.

results.jsonl에서 LLM이 호출된 세그먼트(entry["agent"] is not None)만 추려
agent_elapsed_sec와 api_call_breakdown을 바탕으로:
  - 세그먼트당 전체 LLM 판정 시간
  - 성공 응답 기록의 소요 시간
  - output_tokens와 성공 응답 기록 시간의 상관관계 (피어슨 r)
를 계산해 터미널에 출력한다.

현재 판정은 외부 tool 없이 single-shot으로 동작한다. api_call_breakdown은 성공
응답당 원소 1개를 기록하며, 전송 재시도가 있더라도 실패한 각 시도는 별도 원소로
남기지 않는다. 따라서 이 파일로 실제 API 요청 시도 횟수는 계산할 수 없다.

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

    response_records: list[dict] = []
    segment_elapsed: list[float] = []

    for entry in agent_segments:
        agent = entry["agent"]
        breakdown = agent.get("api_call_breakdown", [])
        response_records.extend(breakdown)
        if isinstance(agent.get("agent_elapsed_sec"), (int, float)):
            segment_elapsed.append(agent["agent_elapsed_sec"])

    if segment_elapsed:
        print("=== 세그먼트당 LLM 판정 시간 ===")
        print(f"  기록 수: {len(segment_elapsed)}")
        print(f"  평균: {mean(segment_elapsed):.3f}초")
        if len(segment_elapsed) > 1:
            print(f"  표준편차: {pstdev(segment_elapsed):.3f}초")
        print(f"  최소/최대: {min(segment_elapsed):.3f}초 / {max(segment_elapsed):.3f}초\n")

    elapsed_list = [
        record["elapsed_sec"]
        for record in response_records
        if isinstance(record.get("elapsed_sec"), (int, float))
    ]
    if not elapsed_list:
        print("성공 API 응답 시간 기록이 없습니다.")
        return

    print("=== 성공 API 응답 기록의 소요 시간 ===")
    print(f"  기록 수: {len(elapsed_list)}")
    print(f"  평균: {mean(elapsed_list):.3f}초")
    if len(elapsed_list) > 1:
        print(f"  표준편차: {pstdev(elapsed_list):.3f}초")
    print(f"  최소/최대: {min(elapsed_list):.3f}초 / {max(elapsed_list):.3f}초")
    print("  주의: 실패한 재시도 횟수는 이 기록으로 계산할 수 없음\n")

    # --- output_tokens vs 왕복 시간 상관관계 ---
    paired_records = [
        record
        for record in response_records
        if record.get("output_tokens") is not None
        and isinstance(record.get("elapsed_sec"), (int, float))
    ]
    output_tokens = [record["output_tokens"] for record in paired_records]
    matched_elapsed = [record["elapsed_sec"] for record in paired_records]
    r = _pearson_r(matched_elapsed, output_tokens)
    print("=== output_tokens vs 성공 응답 기록 시간 상관관계 ===")
    if r is None:
        print("  계산 불가 (데이터 부족 또는 분산 0)")
    else:
        print(f"  피어슨 상관계수 r = {r:.3f}")
        if abs(r) >= 0.6:
            print("  → 강한 상관관계. 원인을 구분하려면 서버 처리/네트워크 시간을 추가 측정해야 함")
        elif abs(r) >= 0.3:
            print("  → 약한/중간 상관관계. 이 값만으로 지연 원인을 특정할 수 없음")
        else:
            print("  → 상관관계가 작음. 이 값만으로 지연 원인을 특정할 수 없음")
    print()

    print("=== 요약 ===")
    print(f"  LLM 호출 세그먼트: {len(agent_segments)}")
    print(f"  성공 응답 기록: {len(response_records)}")
    print(f"  성공 응답 기록당 평균 시간: {mean(elapsed_list):.3f}초")


if __name__ == "__main__":
    main()
