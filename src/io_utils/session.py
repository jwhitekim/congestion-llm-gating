"""
세션 폴더(outputs/<timestamp>/) 및 결과 파일(session.json, results.jsonl) 관리.
main.py는 이 클래스를 통해서만 세션 파일에 접근한다.
"""

import json
from datetime import datetime
from pathlib import Path

import config

OUTPUTS_DIR = Path("outputs")


def _config_snapshot() -> dict:
    return {
        "SURGE_RATIO": config.SURGE_RATIO,
        "SPEED_MIN": config.SPEED_MIN,
        "STAG_SEC": config.STAG_SEC,
        "ZONE_MAX": config.ZONE_MAX,
        "SEGMENT_INTERVAL": config.SEGMENT_INTERVAL,
        "PERCENTILE_HISTORY_MAXLEN": config.PERCENTILE_HISTORY_MAXLEN,
        "MIN_SAMPLES_FOR_PERCENTILE": config.MIN_SAMPLES_FOR_PERCENTILE,
        "DENSITY_LOW_PERCENTILE": config.DENSITY_LOW_PERCENTILE,
        "DENSITY_HIGH_PERCENTILE": config.DENSITY_HIGH_PERCENTILE,
        "ZONE_MAX_PERCENTILE": config.ZONE_MAX_PERCENTILE,
    }


class SessionFileManager:
    def __init__(self, video_path: str, outputs_dir: Path = OUTPUTS_DIR):
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_dir = outputs_dir / self.session_id
        self.session_dir.mkdir(parents=True, exist_ok=True)

        self.session_file = self.session_dir / "session.json"
        self.results_file = self.session_dir / "results.jsonl"
        self.segment_count = 0

        self._session = {
            "session_id": self.session_id,
            "video_path": video_path,
            "started_at": datetime.now().isoformat(),
            "ended_at": None,
            "config_snapshot": _config_snapshot(),
        }
        self._write_session()
        self._results_fh = open(self.results_file, "a", encoding="utf-8")

    def _write_session(self) -> None:
        self.session_file.write_text(json.dumps(self._session, ensure_ascii=False, indent=2))

    def write_segment(
        self, perception_result, trigger_name, trigger_reason, agg_facts, agent_output,
        co_triggered=None, thresholds=None,
    ) -> None:
        entry = {
            "timestamp": perception_result.timestamp,
            "perception": {
                "total": perception_result.total,
                "density": perception_result.density,
                "avg_speed": perception_result.avg_speed,
                "zone_counts": perception_result.zone_counts,
                "zone_density": perception_result.zone_density,
                "concentration": perception_result.concentration,
                "cv_elapsed_sec": perception_result.cv_elapsed_sec,
                "tracks": perception_result.tracks,
            },
            "trigger": trigger_name,
            "trigger_reason": trigger_reason,
            "co_triggered": co_triggered or [],
            "aggregated": {
                "density_delta_ratio": agg_facts.density_delta_ratio,
                "speed_trend": agg_facts.speed_trend,
                "density_slope": agg_facts.density_slope,
                "level": agg_facts.level,
            },
            # 이 세그먼트 판정에 실제로 쓰인 density_low/high, zone_max와 그 출처
            # (fallback|percentile) — trigger/rules.py의 _dynamic_thresholds() 참고.
            # 언제부터 percentile로 전환됐는지 나중에 여기서 확인한다.
            "dynamic_thresholds": thresholds,
            # "agent"는 기존 결과 스키마 필드명. 값은 선택적 LLM 단발 판정 결과다.
            "agent": agent_output,  # 미호출 구간은 null
        }
        self._results_fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self._results_fh.flush()
        self.segment_count += 1

    def close(self) -> None:
        self._results_fh.close()
        self._session["ended_at"] = datetime.now().isoformat()
        self._session["segment_count"] = self.segment_count
        self._write_session()
