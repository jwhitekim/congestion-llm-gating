from collections import deque
import numpy as np
import config
from datatypes import PerceptionResult


class SegmentHistory:
    """
    직전 HISTORY_WINDOW 초의 PerceptionResult를 보관하는 링버퍼.
    변화율·추세 계산의 기준값을 제공한다.
    """

    def __init__(
        self,
        window_sec: float = config.HISTORY_WINDOW,
        interval_sec: float = config.SEGMENT_INTERVAL,
    ):
        max_len = max(1, int(window_sec / interval_sec))
        self._buffer: deque[PerceptionResult] = deque(maxlen=max_len)

    def add(self, result: PerceptionResult) -> None:
        self._buffer.append(result)

    def __len__(self) -> int:
        return len(self._buffer)

    def avg_density(self) -> float:
        if not self._buffer:
            return 0.0
        return sum(r.density for r in self._buffer) / len(self._buffer)

    def avg_speed(self) -> float:
        if not self._buffer:
            return 0.0
        return sum(r.avg_speed for r in self._buffer) / len(self._buffer)

    def speed_trend_with(self, current_speed: float) -> float:
        """
        버퍼 + current를 포함한 선형회귀 기울기.
        양수 = 가속 추세, 음수 = 감속 추세.
        """
        speeds = [r.avg_speed for r in self._buffer] + [current_speed]
        n = len(speeds)
        if n < 2:
            return 0.0
        x_mean = (n - 1) / 2.0
        y_mean = sum(speeds) / n
        num = sum((i - x_mean) * (s - y_mean) for i, s in enumerate(speeds))
        den = sum((i - x_mean) ** 2 for i in range(n))
        return num / den if den else 0.0

    def low_speed_streak_sec(self, speed_min: float, interval_sec: float) -> float:
        """버퍼 끝에서부터 연속으로 speed_min 미만이었던 누적 시간(초)."""
        streak = 0
        for r in reversed(self._buffer):
            if r.avg_speed < speed_min:
                streak += 1
            else:
                break
        return streak * interval_sec

    def density_slope_with(self, current_density: float) -> float:
        """
        버퍼 + current를 포함한 density의 선형회귀 기울기.
        양수 = 밀도 증가 추세, 음수 = 감소 추세.
        """
        densities = [r.density for r in self._buffer] + [current_density]
        n = len(densities)
        if n < 2:
            return 0.0
        x_mean = (n - 1) / 2.0
        y_mean = sum(densities) / n
        num = sum((i - x_mean) * (d - y_mean) for i, d in enumerate(densities))
        den = sum((i - x_mean) ** 2 for i in range(n))
        return num / den if den else 0.0


class ThresholdHistory:
    """
    density/zone_max percentile 계산 전용 긴 히스토리.

    SegmentHistory(HISTORY_WINDOW=30초=직전 6세그먼트, 현재값을 기울기 계산에
    더하면 최대 7포인트)와는 목적이 다르다 — percentile은 이 표본 수로는 너무
    불안정해서 별도로 분리했다.

    무한 누적 대신 최근 PERCENTILE_HISTORY_MAXLEN(기본 100세그먼트 ≈ 8.3분) 창으로
    제한한다. 세션 전체를 무한 누적하면 (1) 긴 세션에서 메모리가 계속 늘고,
    (2) 영상 초반과 후반의 혼잡 패턴이 다를 때 과거 값이 계속 쌓여 최근 상황
    변화에 임계값이 둔감해진다 — 두 이유 다 최근 window로 제한하는 쪽이 낫다고
    판단했다.
    """

    def __init__(self, maxlen: int = config.PERCENTILE_HISTORY_MAXLEN):
        self._density: deque[float] = deque(maxlen=maxlen)
        self._zone_max: deque[int] = deque(maxlen=maxlen)

    def add(self, density: float, zone_counts: dict[str, int]) -> None:
        self._density.append(density)
        self._zone_max.append(max(zone_counts.values()) if zone_counts else 0)

    def __len__(self) -> int:
        return len(self._density)

    def density_percentile(self, p: float) -> float:
        if not self._density:
            return 0.0
        return float(np.percentile(self._density, p))

    def zone_max_percentile(self, p: float) -> float:
        if not self._zone_max:
            return 0.0
        return float(np.percentile(self._zone_max, p))
