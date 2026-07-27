"""
트리거 발화 세그먼트가 "연속된 같은 이벤트의 중복 호출"인지 진단하는 스크립트.

results.jsonl을 세그먼트 순서대로 훑어, trigger != null인 세그먼트 중 연속으로
같은 trigger 타입이 이어지면 하나의 "이벤트 블록"으로 묶는다. 사이에
trigger=null 세그먼트가 끼거나 타입이 바뀌면 블록이 끊긴다. 블록 길이 분포를
보면 같은 이상 상황에 대해 LLM이 얼마나 반복 재호출되고 있는지 가늠할 수 있다
(trigger.md의 "cooldown/episode 상태 없음" 계약 참고).

읽기 전용 분석 스크립트 — results.jsonl을 포함해 어떤 파일도 수정/삭제하지 않는다.

사용법:
  PYTHONPATH=src python scripts/diagnose_trigger_blocks.py [results.jsonl 경로]
  경로를 생략하면 outputs/ 아래 가장 최근 run의 results.jsonl을 사용한다.
"""

import json
import os
import sys
from collections import defaultdict

OUTPUTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "outputs")


def _latest_results_jsonl() -> str:
    runs = sorted(
        d
        for d in os.listdir(OUTPUTS_DIR)
        if os.path.exists(os.path.join(OUTPUTS_DIR, d, "results.jsonl"))
    )
    if not runs:
        raise FileNotFoundError(f"No run with results.jsonl found under {OUTPUTS_DIR}")
    return os.path.join(OUTPUTS_DIR, runs[-1], "results.jsonl")


def _load_segments(path: str) -> list[dict]:
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def _build_blocks(segments: list[dict]) -> list[dict]:
    """연속된 같은 trigger 타입을 블록으로 묶는다. null이 끼거나 타입이 바뀌면 블록 종료."""
    blocks = []
    current = None
    for seg in segments:
        trigger = seg.get("trigger")
        if trigger is None:
            current = None
            continue
        if current is not None and current["type"] == trigger:
            current["length"] += 1
            current["end_ts"] = seg["timestamp"]
        else:
            if current is not None:
                blocks.append(current)
            current = {"type": trigger, "length": 1, "start_ts": seg["timestamp"], "end_ts": seg["timestamp"]}
    if current is not None:
        blocks.append(current)
    return blocks


def _print_report(segments: list[dict], blocks: list[dict]) -> None:
    triggered_segments = sum(1 for s in segments if s.get("trigger") is not None)
    total_blocks = len(blocks)
    lengths = [b["length"] for b in blocks]
    avg_len = sum(lengths) / total_blocks if total_blocks else 0.0
    max_len = max(lengths) if lengths else 0
    singleton_ratio = (sum(1 for l in lengths if l == 1) / total_blocks) if total_blocks else 0.0

    print("=" * 60)
    print("트리거 이벤트 블록 진단")
    print("=" * 60)
    print(f"전체 세그먼트 수:             {len(segments)}")
    print(f"트리거 발화 세그먼트 수:       {triggered_segments}")
    print(f"이벤트 블록 개수:             {total_blocks}")
    print(f"블록당 평균 길이:             {avg_len:.2f}")
    print(f"블록 최대 길이:               {max_len}")
    print(f"길이 1짜리(단발) 블록 비율:     {singleton_ratio:.1%}")

    by_type = defaultdict(list)
    for b in blocks:
        by_type[b["type"]].append(b["length"])

    print()
    print(f"{'trigger 타입':<14}{'블록 수':>8}{'평균 길이':>10}{'최대 길이':>10}")
    print("-" * 42)
    for t in sorted(by_type, key=lambda k: -len(by_type[k])):
        lens = by_type[t]
        print(f"{t:<14}{len(lens):>8}{sum(lens) / len(lens):>10.2f}{max(lens):>10}")


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else _latest_results_jsonl()
    segments = _load_segments(path)
    blocks = _build_blocks(segments)
    print(f"분석 대상: {path}\n")
    _print_report(segments, blocks)


if __name__ == "__main__":
    main()
