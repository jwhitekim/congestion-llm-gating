from typing import Optional
import config
from datatypes import PerceptionResult, AggregatedFacts
from .history import SegmentHistory, ThresholdHistory


def _dynamic_thresholds(threshold_history: ThresholdHistory) -> dict:
    """
    percentile 기반 동적 임계값(density_low/high, zone_max)을 계산한다.

    threshold_history 표본 수가 config.MIN_SAMPLES_FOR_PERCENTILE 미만이면
    콜드스타트로 보고 기존 고정값(config.DENSITY_LOW/HIGH, config.ZONE_MAX)을
    그대로 쓴다 — 표본이 너무 적으면 percentile 자체가 불안정하기 때문이다.
    표본이 쌓이면 percentile로 자동 전환된다. 반환 dict의 "source"로 지금
    어느 쪽이 쓰이고 있는지 세그먼트마다 판별·기록할 수 있다.
    """
    sample_count = len(threshold_history)
    if sample_count < config.MIN_SAMPLES_FOR_PERCENTILE:
        return {
            "source": "fallback",
            "density_low": config.DENSITY_LOW,
            "density_high": config.DENSITY_HIGH,
            "zone_max": config.ZONE_MAX,
            "sample_count": sample_count,
        }
    return {
        "source": "percentile",
        "density_low": threshold_history.density_percentile(config.DENSITY_LOW_PERCENTILE),
        "density_high": threshold_history.density_percentile(config.DENSITY_HIGH_PERCENTILE),
        "zone_max": threshold_history.zone_max_percentile(config.ZONE_MAX_PERCENTILE),
        "sample_count": sample_count,
    }


def _classify_level(density: float, density_low: float, density_high: float) -> str:
    if density < density_low:
        return "low"
    elif density < density_high:
        return "medium"
    return "high"


def evaluate(
    current: PerceptionResult,
    history: SegmentHistory,
    threshold_history: ThresholdHistory,
) -> tuple[Optional[str], Optional[str], AggregatedFacts, list[str], dict]:
    """
    현재 PerceptionResult와 히스토리를 받아 트리거 여부를 판정한다.

    반환: (trigger_name, reason, AggregatedFacts, co_triggered, thresholds)
    트리거 없으면 trigger_name=None, reason=None, co_triggered=[].
    thresholds: 이 세그먼트 판정에 실제로 쓰인 density_low/high, zone_max와
    그 출처(fallback|percentile) — _dynamic_thresholds() 참고. session.jsonl에
    그대로 기록해 언제부터 percentile로 전환됐는지 나중에 확인할 수 있게 한다.

    surge/stagnation/conflict는 변화율·지속시간·추세를 사용하고, hotspot은
    구역 인원이 동적 zone_max를 넘는 순간값 조건이다.

    4개 조건(surge/stagnation/hotspot/conflict)을 모두 독립적으로 평가한다.
    trigger_name은 그중 surge→stagnation→hotspot→conflict 우선순위로 하나만
    골라 반환한다(기존 동작과 100% 동일 — main.py의 LLM 단일 호출 분기와
    프롬프트는 바뀌지 않는다). co_triggered는 trigger_name으로
    선택되지 않았지만 같은 세그먼트에서 동시에 조건을 만족한 다른 트리거
    이름들이다 — 순수 기록용이며 트리거 판정 로직 자체에는 영향을 주지
    않는다(실측: t=455에서 surge와 hotspot이 동시에 만족됐는데 기존
    if/elif 구조에선 surge만 남고 hotspot 발동 사실 자체가 사라졌음).
    """
    thresholds = _dynamic_thresholds(threshold_history)

    avg_density = history.avg_density()
    density_delta_ratio = (
        current.density / avg_density if avg_density > 0 else 1.0
    )
    trend = history.speed_trend_with(current.avg_speed)
    density_slope = history.density_slope_with(current.density)
    level = _classify_level(current.density, thresholds["density_low"], thresholds["density_high"])

    facts = AggregatedFacts(
        current=current,
        density_delta_ratio=density_delta_ratio,
        speed_trend=trend,
        density_slope=density_slope,
        level=level,
    )

    # 현재값을 히스토리에 추가 (delta/percentile 계산 이후에 추가해야 직전 평균·분포가
    # 기준이 됨 — threshold_history도 SegmentHistory와 동일한 순서 규칙을 따른다)
    history.add(current)
    threshold_history.add(current.density, current.zone_counts)

    # --- 논문 표 1의 네 트리거 조건 ---
    # 4개 다 독립적으로 판정해 matched에 모아둔다(첫 매치에서 멈추지 않음).
    # dict 삽입 순서 = surge→stagnation→hotspot→conflict 우선순위 순서와 같으므로
    # 아래에서 우선순위를 고를 때도, co_triggered를 나열할 때도 이 순서를 그대로 쓴다.
    matched: dict[str, str] = {}

    # 1. Surge: density가 직전 이동평균의 SURGE_RATIO 배 초과
    if len(history) >= 2 and density_delta_ratio > config.SURGE_RATIO:
        matched["surge"] = (
            f"density {current.density:.1f} > "
            f"avg {avg_density:.1f} × {config.SURGE_RATIO} "
            f"(ratio={density_delta_ratio:.2f})"
        )

    # 2. Stagnation: 속도가 SPEED_MIN 미만으로 STAG_SEC 초 이상 지속
    history_streak = history.low_speed_streak_sec(config.SPEED_MIN, config.SEGMENT_INTERVAL)
    # current가 이미 history에 추가됐으므로 streak에 포함됨
    if history_streak >= config.STAG_SEC:
        matched["stagnation"] = (
            f"avg_speed {current.avg_speed:.2f} px/s < {config.SPEED_MIN} "
            f"for {history_streak:.0f}s"
        )

    # 3. Hotspot: 한 구역 인원이 (percentile 기반, 콜드스타트 시 고정값) zone_max 초과
    if current.zone_counts:
        hotspot_zone = max(current.zone_counts, key=current.zone_counts.get)
        hotspot_count = current.zone_counts[hotspot_zone]
        if hotspot_count > thresholds["zone_max"]:
            matched["hotspot"] = (
                f"hotspot: {hotspot_zone}구역 {hotspot_count}명 > 임계 "
                f"{thresholds['zone_max']:.1f} ({thresholds['source']})"
            )

    # 4. Conflict: 순간값 기준 level은 "low"인데 추세(density_slope)는 가파르게
    #    상승 중인 경계 사례. surge는 직전 평균 대비 비율이라 완만하지만 꾸준한
    #    상승은 못 잡고, level은 순간 density만 보므로 추세를 모른다 — 두 규칙이
    #    서로 다른 답을 내는 지점이라 규칙만으로는 판정을 내릴 수 없다.
    #    이런 사례를 LLM에 넘겨 해석하게 하는 것이 이 트리거의 존재 이유다.
    #    current.total > 0 가드: density_slope_with()는 HISTORY_WINDOW(30초, 7세그먼트)
    #    전체에 대한 선형회귀라서 "스파이크 후 원래대로 복귀"한 패턴도 양수 기울기로
    #    잡힌다(실측: t=280, density=0.0인데 직전 윈도우 [0,0,0,17.34,0,34.82,0]의
    #    slope=2.4872로 오탐 — LLM이 매번 "노이즈"라고 판정하는데도 API 호출은
    #    이미 발생). 지금 아무도 없는데(total=0) 추세가 상승 중이라는 판정 자체가
    #    의미 없다 — 추세가 향하는 대상(현재 밀도)이 0이면 애초에 판정 불가.
    if level == "low" and density_slope > config.CONFLICT_SLOPE_MIN and current.total > 0:
        matched["conflict"] = (
            f"conflict: level={level}이지만 density_slope={density_slope:.2f} "
            f"> 임계 {config.CONFLICT_SLOPE_MIN} — 순간값과 추세 판정이 상충"
        )

    for name in ("surge", "stagnation", "hotspot", "conflict"):
        if name in matched:
            co_triggered = [n for n in matched if n != name]
            return name, matched[name], facts, co_triggered, thresholds

    return None, None, facts, [], thresholds
