"""
zone별 정규화 밀도 + 전체 집중도 계산.

perception 계층의 상시 파이프라인 일부다. 매 세그먼트 pipeline._build_result()에서
규칙 기반으로 계산되며 LLM은 전혀 개입하지 않는다. agent/tools/의 "tool"(향후 LLM
판정 과정에서 필요에 따라 호출할 수 있는 것)과 혼동하지 말 것 — 이 모듈의 함수는
perception이 매 세그먼트 자동으로 실행해 PerceptionResult에 실어 보내는 관측값 생산기다.
"""


def calc_zone_density(zone_counts: dict[str, int], zones: dict[str, tuple[float, float]]) -> dict[str, float]:
    """
    zone별 인원을 zone 폭(정규화된 x축 비율)으로 나눈 근사 밀도.

    한계: 이는 카메라 각도/거리 기준의 실제 면적 정규화가 아니다. config.ZONES는
    화면상의 x축 구간 비율일 뿐이며, 원근(perspective) 때문에 같은 x축 폭이라도
    카메라에서 먼 구역과 가까운 구역의 실제 바닥 면적은 다르다. 카메라 캘리브레이션
    (호모그래피 등) 없이는 정확한 면적 정규화가 불가능하므로, 이 값은 "화면 폭당
    인원 수"의 근사치로만 취급해야 한다.
    """
    density = {}
    for zone, count in zone_counts.items():
        lo, hi = zones.get(zone, (0.0, 1.0))
        width = max(hi - lo, 1e-6)
        density[zone] = count / width
    return density


def calc_concentration(zone_counts: dict[str, int]) -> float:
    """
    zone 간 분포 집중도 (Herfindahl-Hirschman 지수).

    각 zone이 전체 인원에서 차지하는 비중(share)의 제곱합.
    인원이 zone마다 고르게 분산되어 있으면 1/구역수에 가깝고, 한 구역에 전원이
    몰려 있으면 1.0에 가깝다. 전체 인원이 0명이면 0.0.
    """
    total = sum(zone_counts.values())
    if total == 0:
        return 0.0
    return sum((count / total) ** 2 for count in zone_counts.values())
