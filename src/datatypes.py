from dataclasses import dataclass, field


@dataclass
class PerceptionResult:
    """한 세그먼트의 객관적 사실. 이미지/픽셀 필드 없음."""
    timestamp: float            # 세그먼트 시작 시각(초)
    total: int                  # 총 인원
    density: float              # Line Density 값
    avg_speed: float            # track 평균 이동 속도 (px/s)
    zone_counts: dict[str, int] # 구역별 인원
    zone_density: dict[str, float]  # 구역별 정규화 밀도 (근사치, perception/zone_metrics.py 참고)
    concentration: float        # 구역 간 분포 집중도 (Herfindahl-Hirschman 지수)
    tracks: list[dict]          # raw: track_id, center, bbox (연구용 보존)
    cv_elapsed_sec: float        # 이 세그먼트 구간 동안 detect+track에 소요된 실제 시간 (초)


@dataclass
class AggregatedFacts:
    """규칙 기반 이벤트 게이트와 선택적 LLM 판정에 전달되는 집계 관측값."""
    current: PerceptionResult
    density_delta_ratio: float  # current.density / 직전 이동평균 (1.0 = 변화 없음)
    speed_trend: float          # 양수 = 가속, 음수 = 감속 (선형회귀 기울기)
    density_slope: float        # 양수 = 밀도 증가 추세, 음수 = 감소 추세 (선형회귀 기울기)
    level: str                  # "low" | "medium" | "high"


# PerceptionResult/AggregatedFacts 필드를 LLM에게 어떤 경로로 노출할지 결정하는
# 유일한 지점. 이전에는 이 판단이 track_people tool 안, _facts_to_text 안 등
# 코드 곳곳에 흩어져 즉흥적으로 결정되고 반복적으로 뒤집혔다 — 여기 한 곳으로
# 모아 강제한다. 세 집합은 서로 배타적이어야 하며 각 필드는 정확히 하나에만
# 속해야 한다.
#
# always/tool 분류 기준(매번 필요한 aggregate vs 가끔만 필요한 granular)은
# 자동으로 답을 주지 않으며 여전히 사람 판단이 필요함. NOT_EXPOSED는 애초에
# 판단 입력이 아닌 로깅/연구용 필드.

ALWAYS_VISIBLE = {
    "total", "density", "avg_speed", "zone_counts",
    "zone_density", "concentration", "level",
    "density_slope", "density_delta_ratio", "speed_trend",
    # density_delta_ratio(직전 평균 대비 순간 스파이크 비율)와 density_slope(구간
    # 전체 회귀 추세)는 서로 다른 정보다 — conflict 트리거 자체가 이 둘이 갈리는
    # 지점(완만하지만 꾸준한 상승은 delta_ratio로 못 잡고, level/순간값은 추세를
    # 모름)을 잡으려고 만들어졌다(trigger/rules.py 4번 조건 주석 참고). speed_trend도
    # avg_speed(현재 세그먼트 순간값)와 다른 시간창(최대 35s 회귀)이라 별개 정보.
    # 처음 이 세트를 작성할 때 이 둘을 빠뜨린 건 의도적 제외가 아니라 실수였음.
}  # 매 트리거마다 LLM에게 텍스트로 항상 보여주는 aggregate 사실.

TOOL_ONLY: set[str] = set()  # 지금 비어있음. granular/개별 데이터(예: 향후
                              # 행동분석/자세추정 등 방법론 추가 시 track별
                              # 요약 데이터)가 생기기 전까지는 비워둘 것 —
                              # 미리 채우지 말 것.

NOT_EXPOSED = {
    "tracks", "cv_elapsed_sec",
    "timestamp",  # 판단 입력이 아니므로 tracks/cv_elapsed_sec와 같은 이유로
                  # 추가함(사용자가 준 목록엔 없었던 항목 — 세그먼트
                  # 시각은 congestion 판단과 무관한 로깅/식별용이라 같은
                  # 분류가 맞다고 판단했다. 의도와 다르면 알려줄 것).
}  # LLM에 어떤 경로로도 안 감. tracks는 tool_raw 연구 보존용 원본 좌표,
   # cv_elapsed_sec는 성능 로깅용. 둘 다 판단 입력이 아니므로 always/tool
   # 어느 쪽에도 넣지 말 것.

assert (
    not (ALWAYS_VISIBLE & TOOL_ONLY)
    and not (ALWAYS_VISIBLE & NOT_EXPOSED)
    and not (TOOL_ONLY & NOT_EXPOSED)
), "ALWAYS_VISIBLE/TOOL_ONLY/NOT_EXPOSED는 서로 배타적이어야 한다"
