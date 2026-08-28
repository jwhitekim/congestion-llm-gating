import os
from dotenv import load_dotenv

load_dotenv()

# --- Model ---
MODEL_DIR = "models"
LEGACY_MODEL_DIR = "legacy_weights"  # 기본으로는 안 쓰지만 비교/롤백용으로 남겨둔 가중치
YOLO_BASE_MODEL_NAME = "yolov8m.pt"
YOLO_SMALL_MODEL_NAME = "yolov8s.pt"
YOLO_FINE_TUNED_MODEL_NAME = "capdi-y8m-640-crowdah-v1-fp32-pt-20250609.pt"

# 실제 로드에 쓰이는 모델 선택. "base" | "small" | "fine_tuned".
# capdi만 비교/롤백용으로 legacy_weights/에 따로 보관한다.
YOLO_MODEL_CHOICE = os.getenv("YOLO_MODEL_CHOICE", "base")
_YOLO_MODEL_NAMES = {
    "base": YOLO_BASE_MODEL_NAME,
    "small": YOLO_SMALL_MODEL_NAME,
    "fine_tuned": YOLO_FINE_TUNED_MODEL_NAME,
}
ACTIVE_YOLO_MODEL = _YOLO_MODEL_NAMES[YOLO_MODEL_CHOICE]
ACTIVE_MODEL_DIR = LEGACY_MODEL_DIR if YOLO_MODEL_CHOICE == "fine_tuned" else MODEL_DIR

# --- Pipeline ---
SEGMENT_INTERVAL = 5.0  # seconds between PerceptionResult emissions

# Zones: normalized x-axis fractions (left→right)
ZONES: dict[str, tuple[float, float]] = {
    "A": (0.00, 0.33),
    "B": (0.33, 0.67),
    "C": (0.67, 1.00),
}

# --- Trigger ---
HISTORY_WINDOW = 30.0   # seconds of history kept in ring buffer
SURGE_RATIO   = 1.4     # density > avg * this  →  surge trigger
SPEED_MIN     = 0.5     # px/s; below this counts as stagnant
STAG_SEC      = 10.0    # stagnation must persist this many seconds to trigger
ZONE_MAX      = 8       # people in one zone > this  →  hotspot trigger
CONFLICT_SLOPE_MIN = 0.4  # density_slope > this while level=="low"  →  conflict trigger

# Congestion level thresholds (used by trigger/rules.py to set AggregatedFacts.level).
# 콜드스타트 fallback 값이기도 하다 — 아래 percentile 히스토리 표본이
# MIN_SAMPLES_FOR_PERCENTILE 미만일 때 이 고정값을 그대로 쓴다.
DENSITY_LOW  = 15.0
DENSITY_HIGH = 35.0

# --- Dynamic threshold (percentile 기반, 콜드스타트 fallback 포함) ---
# 디텍터가 head→전신으로 바뀌면서 density 스케일이 달라져(약 0~140 → 0~350대)
# 고정 임계값(DENSITY_LOW/HIGH, ZONE_MAX)이 과다발동을 일으킨 문제를 percentile
# 기반 동적 임계값으로 완화한다. trigger/history.py의 ThresholdHistory 참고.
PERCENTILE_HISTORY_MAXLEN = 100  # 세그먼트 수. SEGMENT_INTERVAL=5초 기준 약 8.3분 창.
MIN_SAMPLES_FOR_PERCENTILE = 20  # 이 미만이면 DENSITY_LOW/HIGH, ZONE_MAX 고정값 사용
DENSITY_LOW_PERCENTILE = 50
DENSITY_HIGH_PERCENTILE = 90
ZONE_MAX_PERCENTILE = 90

# --- Selective LLM judgment (legacy AGENT_* identifiers retained) ---
AGENT_PROVIDER = os.getenv("AGENT_PROVIDER", "anthropic")  # "anthropic" | "gemini"
AGENT_MAX_RETRIES = 3        # API 레벨 실패(네트워크/rate limit/서버 오류) 재시도 횟수
AGENT_RETRY_BACKOFF_SEC = 1.0  # 첫 재시도 대기 시간(초). 매 재시도마다 2배 증가

ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
