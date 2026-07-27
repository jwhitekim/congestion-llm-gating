import time
from collections import defaultdict, deque
from typing import Optional
import numpy as np

import config
from datatypes import PerceptionResult
from .detector import Detector
from .tracker import Tracker
from .density import calc_spatial_density, calc_avg_speed
from .zone_metrics import calc_zone_density, calc_concentration


class PerceptionPipeline:
    """
    영상 프레임 스트림 → PerceptionResult 스트림.

    모든 프레임을 tracker에 먹여 track 연속성을 유지하되,
    SEGMENT_INTERVAL 초마다 한 번만 PerceptionResult를 방출한다.

    의존 방향: perception → types 만.
    """

    def __init__(self, fps: float = 30.0):
        self.detector = Detector()
        self.tracker = Tracker(frame_rate=fps)
        self.track_trails: dict[int, deque] = defaultdict(lambda: deque(maxlen=30))

        self._fps = fps
        self._segment_start: float = 0.0
        self._segment_cv_elapsed: float = 0.0  # 이번 세그먼트 구간의 detect+track 누적 시간
        self._initialized = False  # 첫 프레임 타임스탬프로 segment_start 세팅
        self._last_tracked = []
        self._last_frame_width: int = 0
        self._last_timestamp: Optional[float] = None

    def feed(self, timestamp: float, frame: np.ndarray) -> Optional[PerceptionResult]:
        """
        프레임 하나를 처리한다.
        SEGMENT_INTERVAL이 지났으면 PerceptionResult를 반환, 아니면 None.
        """
        if not self._initialized:
            self._segment_start = timestamp
            self._initialized = True

        h, w = frame.shape[:2]
        frame_start = time.perf_counter()
        detections = self.detector.detect(frame)
        tracked = self.tracker.update(detections)
        self._segment_cv_elapsed += time.perf_counter() - frame_start

        for obj in tracked:
            track_id = int(obj[4])
            cx = (int(obj[0]) + int(obj[2])) // 2
            cy = (int(obj[1]) + int(obj[3])) // 2
            self.track_trails[track_id].append((cx, cy))

        self._last_tracked = tracked
        self._last_frame_width = w
        self._last_timestamp = timestamp

        if timestamp - self._segment_start >= config.SEGMENT_INTERVAL:
            result = self._build_result(timestamp, tracked, w, self._segment_cv_elapsed)
            self._segment_start = timestamp
            self._segment_cv_elapsed = 0.0
            return result

        return None

    def flush(self) -> Optional[PerceptionResult]:
        """
        영상 스트림이 끝난 뒤 SEGMENT_INTERVAL을 채우지 못한 마지막 자투리 구간을 방출한다.
        방출할 자투리가 없으면 None.
        """
        if self._last_timestamp is None or self._last_timestamp <= self._segment_start:
            return None

        result = self._build_result(
            self._last_timestamp, self._last_tracked, self._last_frame_width, self._segment_cv_elapsed
        )
        self._segment_start = self._last_timestamp
        self._segment_cv_elapsed = 0.0
        return result

    def _build_result(self, timestamp: float, tracked, frame_width: int, cv_elapsed_sec: float) -> PerceptionResult:
        total = len(tracked)
        density = calc_spatial_density(tracked)
        avg_speed = calc_avg_speed(self.track_trails, self._fps)
        zone_counts = self._zone_counts(tracked, frame_width)
        zone_density = calc_zone_density(zone_counts, config.ZONES)
        concentration = calc_concentration(zone_counts)
        tracks = [
            {
                "track_id": int(obj[4]),
                "center": ((int(obj[0]) + int(obj[2])) // 2, (int(obj[1]) + int(obj[3])) // 2),
                "bbox": [int(obj[0]), int(obj[1]), int(obj[2]), int(obj[3])],
            }
            for obj in tracked
        ]
        return PerceptionResult(
            timestamp=timestamp,
            total=total,
            density=density,
            avg_speed=avg_speed,
            zone_counts=zone_counts,
            zone_density=zone_density,
            concentration=concentration,
            tracks=tracks,
            cv_elapsed_sec=round(cv_elapsed_sec, 3),
        )

    def _zone_counts(self, tracked, frame_width: int) -> dict[str, int]:
        counts = {zone: 0 for zone in config.ZONES}
        for obj in tracked:
            cx_norm = ((obj[0] + obj[2]) / 2) / frame_width
            for zone, (lo, hi) in config.ZONES.items():
                if lo <= cx_norm < hi:
                    counts[zone] += 1
                    break
        return counts
