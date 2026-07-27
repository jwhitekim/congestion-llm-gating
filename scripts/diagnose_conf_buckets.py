"""
Phase 2 Step 1에서 수행한 과거 진단 — tracker 유실률의 원인이
"OCSort use_byte=False 때문에 conf 0.07~0.3 구간 detection이 통째로
버려지는 것"이라는 가설을 정량 검증하는 스크립트.

현재 `perception/tracker.py`는 이 진단 결과를 반영해 `use_byte=True`다.

tracker.py 주석에 이미 적혀있던 사실: OCSort 기본값 use_byte=False라서 conf가
det_thresh(0.3) 미만인 detection은 새 트랙 생성에도, 기존 트랙 매칭에도 전혀
쓰이지 않고 버려진다. detector conf(0.07)와 tracker det_thresh(0.3) 사이 구간이
raw_box 중 얼마나 되는지를 세어, 이 구간 비율이 큰지 확인한다.

diagnose_detector.py의 Detector/_RawDetector/VIDEO_PATH/COMPARE_FRAMES를 그대로
재사용한다 — 같은 영상, 같은 프레임 수, 같은 detect() 인터페이스라야 이전
raw_box/confirmed_track 결과와 비교 가능하다.

이 스크립트 자체는 raw_box를 confidence 버킷으로만 나눠 세며 tracker를 호출하지
않는다. 아래 설명의 Step 2는 당시 진단 순서를 가리킨다.

사용법: YOLO_MODEL_CHOICE=fine_tuned PYTHONPATH=src python scripts/diagnose_conf_buckets.py
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import cv2

from src import config
from src.perception.detector import Detector
from diagnose_detector import _RawDetector, VIDEO_PATH, COMPARE_FRAMES

BUCKET_SPLIT = 0.3  # tracker.py의 det_thresh와 동일 — 이 값 기준으로 A/B 버킷을 나눈다


def _bucket_per_frame(detector, video_path: str, num_frames: int) -> list[tuple[int, int]]:
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise IOError(f"Cannot open video: {video_path}")

    per_frame = []
    try:
        for frame_idx in range(num_frames):
            ret, frame = cap.read()
            if not ret:
                break
            detections = detector.detect(frame)
            confs = detections[:, 4].tolist() if len(detections) else []
            bucket_a = sum(1 for c in confs if c < BUCKET_SPLIT)
            bucket_b = sum(1 for c in confs if c >= BUCKET_SPLIT)
            per_frame.append((bucket_a, bucket_b))
    finally:
        cap.release()
    return per_frame


def _report(label: str, per_frame: list[tuple[int, int]]) -> None:
    n = len(per_frame)
    total_a = sum(a for a, _ in per_frame)
    total_b = sum(b for _, b in per_frame)
    total = total_a + total_b
    avg_a = total_a / n
    avg_b = total_b / n
    ratio_a = total_a / total if total else 0.0
    print(f"\n{'=' * 60}\n[{label}] conf bucket 분포 (frame_rate={n})\n{'=' * 60}")
    print(f"  bucket A (0.07<=conf<0.3): avg/frame={avg_a:.1f}  전체 비율={ratio_a:.1%}")
    print(f"  bucket B (conf>=0.3):      avg/frame={avg_b:.1f}  전체 비율={1 - ratio_a:.1%}")


def main() -> None:
    base_path = os.path.join(config.MODEL_DIR, config.YOLO_BASE_MODEL_NAME)

    capdi_buckets = _bucket_per_frame(Detector(), VIDEO_PATH, COMPARE_FRAMES)
    coco_buckets = _bucket_per_frame(_RawDetector(base_path), VIDEO_PATH, COMPARE_FRAMES)

    _report("capdi", capdi_buckets)
    _report("coco-base (person-only)", coco_buckets)


if __name__ == "__main__":
    main()
