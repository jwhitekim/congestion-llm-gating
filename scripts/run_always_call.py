"""
Always-call 베이스라인 실험: 트리거 게이팅과 무관하게 매 세그먼트마다 LLM을 호출한다.

목적: 트리거 기반 게이팅(trigger/rules.py의 evaluate())이 없다면 LLM이 매
세그먼트를 어떻게 판정하는지 비교하기 위한 베이스라인. 검출기(COCO 전신
검출)/트래커(OC-SORT use_byte=True)/ThresholdHistory percentile 임계값 계산은
기존 파이프라인과 동일하다 — main.py의 루프를 복제하되 "trigger_name이
None이면 LLM을 호출하지 않는다"는 게이팅 분기만 뺐다.

직접적인 라벨 프라이밍 완화: 규칙이 실제로 안 맞은 세그먼트에서는
trigger_reason에 "정기 스캔"이라는 중립적 문구를 쓴다. 다만 공통 system
prompt는 여전히 규칙 기반 트리거가 이상 신호를 감지했다고 설명하므로 프라이밍을
완전히 제거한 대조군은 아니다. 논문 결과를 해석할 때 트리거 정보가 LLM 판정에
영향을 줄 수 있다는 한계를 함께 둔다.

results.jsonl 최상단 trigger/trigger_reason 필드는 실제 규칙 판정 결과를 그대로
남긴다(규칙 미매치면 None) — LLM에게 보낸 라벨과는 별개다. 기존 `agent` 결과 블록에는
rule_matched(bool)를 추가로 기록해 "규칙이 실제로 맞아서 불렸는지 / 게이팅
없이 강제로 불렸는지"를 사후 분석에서 구분할 수 있게 한다 — 이 필드는 LLM
호출 이후에 채워 넣으므로 프롬프트에는 노출되지 않는다.

main.py / config.py / io_utils/session.py / agent/loop.py / trigger/rules.py는
전혀 수정하지 않는다 — 이 스크립트 하나만 추가.

사용법: PYTHONPATH=src python scripts/run_always_call.py [video_path]
        (video_path 생략 시 videos/department_store.mp4)
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

# LLM 프롬프트용 중립 라벨 — 규칙 미매치 세그먼트에서 trigger_name/trigger_reason 대신 사용.
# "실험"/"베이스라인"/"강제 호출" 같은 메타 정보는 넣지 않아 직접적 메타 프라이밍을 줄인다.
NEUTRAL_LABEL = "periodic"
NEUTRAL_REASON = "정기 스캔"


def main(video_path: str) -> None:
    session = SessionFileManager(video_path)
    log = GetLogger(session.session_id, str(session.session_dir / "run.log"))
    log.info(f"세션 시작 (always-call 베이스라인): video={video_path}")

    try:
        fps = get_video_fps(video_path)
        pipeline = PerceptionPipeline(fps=fps)
        history = SegmentHistory()
        threshold_history = ThresholdHistory()

        def process_segment(perception_result) -> None:
            # ── 2단계: Trigger (항상 실행, main.py와 동일 — 규칙 로직 안 바뀜) ──
            trigger_name, trigger_reason, agg_facts, co_triggered, thresholds = rules.evaluate(
                perception_result, history, threshold_history
            )
            rule_matched = trigger_name is not None
            log.info(
                f"segment t={perception_result.timestamp:.1f}s "
                f"total={perception_result.total} density={perception_result.density:.2f} "
                f"trigger={trigger_name or '-'} thresholds={thresholds['source']} (always-call)"
            )

            # ── 3단계: LLM 단발 판정 — 게이팅 없이 매 세그먼트 호출 ──────
            # LLM에게 보내는 라벨/사유만 중립화하고, 그 외 agent_loop.run() 호출
            # 방식(agg_facts, zone_max 등)은 선택적 호출 경로와 동일하게 유지한다.
            call_label = trigger_name if rule_matched else NEUTRAL_LABEL
            call_reason = trigger_reason if rule_matched else NEUTRAL_REASON

            agent_start = time.perf_counter()
            agent_output = agent_loop.run(
                agg_facts, call_label, call_reason, thresholds["zone_max"], log=log
            )
            agent_elapsed = time.perf_counter() - agent_start
            agent_output["agent_elapsed_sec"] = round(agent_elapsed, 3)
            agent_output["api_round_trips"] = len(agent_output["api_call_breakdown"])
            # 사후 분석 전용 필드 — LLM 호출 이후에 채워 넣으므로 프롬프트에는 노출되지 않는다.
            agent_output["rule_matched"] = rule_matched

            # ── 터미널 출력 (사람용) ────────────────────────────────────────
            report_segment(perception_result, trigger_name, trigger_reason, agg_facts.level, agent_output)

            # ── results.jsonl 누적 — trigger/trigger_reason은 실제 규칙 판정 결과
            # 그대로 기록(규칙 미매치면 None). LLM에게 보낸 중립 라벨과는 별개다.
            session.write_segment(
                perception_result, trigger_name, trigger_reason, agg_facts, agent_output, co_triggered, thresholds
            )

        for timestamp, frame in iter_frames(video_path):
            # ── 1단계: Perception (항상 실행, main.py와 동일) ──────────────
            perception_result = pipeline.feed(timestamp, frame)
            if perception_result is None:
                continue
            process_segment(perception_result)

        # ── 영상 종료: SEGMENT_INTERVAL을 못 채운 마지막 자투리 구간 처리 (main.py와 동일) ──
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
