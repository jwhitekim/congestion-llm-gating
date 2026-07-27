"""
파이프라인 오케스트레이션.

설계 원칙:
  perception → trigger → (트리거 구간만) LLM 단발 판정

인지 계층은 모든 구간에서 관측값을 계산하고, 규칙 기반 이벤트 게이트가
선택한 구간에서만 텍스트 LLM을 한 번 호출하는 흐름이 명확히 보여야 한다.
"""

import sys
import time

from io_utils.sampler import get_video_fps, iter_frames
from io_utils.reporter import report_segment
from io_utils.session import SessionFileManager
from perception.pipeline import PerceptionPipeline
from trigger.history import SegmentHistory, ThresholdHistory
from trigger import rules
from agent import loop as agent_loop
from logger import GetLogger


def main(video_path: str) -> None:
    session = SessionFileManager(video_path)
    log = GetLogger(session.session_id, str(session.session_dir / "run.log"))
    log.info(f"세션 시작: video={video_path}")

    try:
        fps = get_video_fps(video_path)
        pipeline = PerceptionPipeline(fps=fps)
        history = SegmentHistory()
        threshold_history = ThresholdHistory()

        def process_segment(perception_result) -> None:
            # ── 2단계: Trigger (항상 실행) ─────────────────────────────────
            trigger_name, trigger_reason, agg_facts, co_triggered, thresholds = rules.evaluate(
                perception_result, history, threshold_history
            )
            log.info(
                f"segment t={perception_result.timestamp:.1f}s "
                f"total={perception_result.total} density={perception_result.density:.2f} "
                f"trigger={trigger_name or '-'} thresholds={thresholds['source']}"
            )

            # ── 3단계: 선택적 LLM 단발 판정 (트리거 구간만) ────────────────
            agent_output = None
            if trigger_name is not None:
                agent_start = time.perf_counter()
                agent_output = agent_loop.run(
                    agg_facts, trigger_name, trigger_reason, thresholds["zone_max"], log=log
                )
                agent_elapsed = time.perf_counter() - agent_start
                agent_output["agent_elapsed_sec"] = round(agent_elapsed, 3)
                agent_output["api_round_trips"] = len(agent_output["api_call_breakdown"])
            # trigger_name이 None이면 LLM을 호출하지 않고 관측값만 기록한다.
            # 이 분기가 논문의 규칙 기반 선택적 호출을 구현한다.

            # ── 터미널 출력 (사람용) ────────────────────────────────────────
            report_segment(perception_result, trigger_name, trigger_reason, agg_facts.level, agent_output)

            # ── results.jsonl 누적 (분석용, tool_raw 포함 전체 보존) ─────────
            session.write_segment(
                perception_result, trigger_name, trigger_reason, agg_facts, agent_output, co_triggered, thresholds
            )

        for timestamp, frame in iter_frames(video_path):
            # ── 1단계: Perception (항상 실행) ──────────────────────────────
            perception_result = pipeline.feed(timestamp, frame)
            if perception_result is None:
                continue  # 아직 세그먼트 인터벌 미달
            process_segment(perception_result)

        # ── 영상 종료: SEGMENT_INTERVAL을 못 채운 마지막 자투리 구간 처리 ──
        tail_result = pipeline.flush()
        if tail_result is not None:
            process_segment(tail_result)
    except Exception:
        log.exception("파이프라인 실행 중 예외 발생")
        raise
    finally:
        session.close()

    log.info(f"세션 종료: segment_count={session.segment_count}")
    print(f"\n결과 저장: {session.results_file} ({session.segment_count}개 세그먼트)")


if __name__ == "__main__":
    video = sys.argv[1] if len(sys.argv) > 1 else "videos/department_store.mp4"
    main(video)
