"""
capdi 모델이 사람을 거의 못 잡는 문제를 진단하는 스크립트.

capdi(config.YOLO_FINE_TUNED_MODEL_NAME)와 COCO 기본 가중치
(config.YOLO_BASE_MODEL_NAME)를 같은 프레임에 대해 conf=0.01(사실상 무제한)로 돌려
비교한다. Detector 클래스를 거치지 않고 YOLO를 직접 호출한다 — model.names,
result.plot() 등 진단에 필요한 raw 접근이 필요해서다.

추가로 앞 COMPARE_FRAMES 프레임을 순회하며 detector.detect()의 raw box 개수와
tracker.update()의 confirmed track 개수를 비교한다. raw box는 많은데
confirmed track이 적으면 detector가 아니라 tracker(OC-SORT) 단계에서
유실될 가능성을 점검해야 한다. `Detector`는 `YOLO_MODEL_CHOICE`에 따라 모델을
고르므로 capdi 경로를 진단하려면 `YOLO_MODEL_CHOICE=fine_tuned`로 실행한다.
COCO 비교군은 동일한 detect() 인터페이스를 갖는 _RawDetector로 모델 경로만
바꿔 낀다. tracker는 두 모델 모두 perception.tracker.Tracker를 사용한다.

사용법: YOLO_MODEL_CHOICE=fine_tuned PYTHONPATH=src python scripts/diagnose_detector.py [프레임번호]
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))  # src/를 PYTHONPATH에 추가

import cv2
import torch
from ultralytics import YOLO

from src import config
from src.perception.detector import Detector
from src.perception.tracker import Tracker
from src.io_utils.sampler import get_video_fps

VIDEO_PATH = "videos/department_store.mp4"
OUTPUT_DIR = "outputs"
PROBE_CONF = 0.01
COMPARE_FRAMES = 30


def _grab_frame(video_path: str, frame_idx: int):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise IOError(f"Cannot open video: {video_path}")
    try:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if not ret:
            raise IOError(f"프레임 {frame_idx}를 읽을 수 없음: {video_path}")
        return frame
    finally:
        cap.release()


def _diagnose(label: str, model_path: str, frame, output_path: str) -> None:
    print(f"\n{'=' * 60}\n[{label}] {model_path}\n{'=' * 60}")

    model = YOLO(model_path)
    print(f"model.names: {model.names}")

    result = model.predict(frame, conf=PROBE_CONF, verbose=False)[0]
    boxes = result.boxes

    print(f"검출된 box 개수: {len(boxes)}")
    for i in range(len(boxes)):
        conf = boxes.conf[i].item()
        cls = int(boxes.cls[i].item())
        cls_name = model.names.get(cls, f"unknown({cls})")
        print(f"  box[{i}]: conf={conf:.4f} cls={cls}({cls_name})")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    plotted = result.plot()
    cv2.imwrite(output_path, plotted)
    print(f"시각화 저장: {output_path}")


class _RawDetector:
    """
    perception.detector.Detector와 동일한 detect() 인터페이스를 갖되 모델 경로를
    바꿔 낄 수 있게 한 진단 전용 래퍼. 실제 Detector는 전역
    config.ACTIVE_YOLO_MODEL을 사용하므로 한 프로세스에서 두 가중치를 동시에
    비교하기 위해 필요하다.
    """

    def __init__(self, model_path: str):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self._model = YOLO(model_path).to(self.device)

    def detect(self, frame, conf: float = 0.07) -> torch.Tensor:
        result = self._model.predict(
            source=frame,
            conf=conf,
            device=self.device,
            classes=[0],
            verbose=False,
        )[0]

        boxes = result.boxes.xyxy
        confs = result.boxes.conf
        classes = result.boxes.cls

        if isinstance(boxes, torch.Tensor):
            boxes = boxes.tolist()
        if isinstance(confs, torch.Tensor):
            confs = confs.tolist()
        if isinstance(classes, torch.Tensor):
            classes = classes.tolist()

        data = [b + [c, cl] for b, c, cl in zip(boxes, confs, classes)]
        return torch.tensor(data, dtype=torch.float32) if data else torch.zeros((0, 6))


def _compare_detector_vs_tracker(label: str, detector, video_path: str, fps: float, num_frames: int) -> None:
    print(f"\n{'=' * 60}\n[{label}] detector vs tracker 비교 (raw box → confirmed track)\n{'=' * 60}")

    tracker = Tracker(frame_rate=fps)
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise IOError(f"Cannot open video: {video_path}")

    try:
        for frame_idx in range(num_frames):
            ret, frame = cap.read()
            if not ret:
                print(f"프레임 {frame_idx}에서 영상 종료")
                break

            detections = detector.detect(frame)
            tracked = tracker.update(detections)
            raw_count = len(detections)
            confirmed_count = len(tracked)
            gap = raw_count - confirmed_count
            print(
                f"  frame[{frame_idx:3d}] raw_box={raw_count:3d} "
                f"confirmed_track={confirmed_count:3d} (diff={gap:+d})"
            )
    finally:
        cap.release()

    # raw box는 꾸준히 나오는데 confirmed track만 낮게 유지되면 detector가 아니라
    # tracker(OC-SORT의 confirmation/association 로직) 단계에서 유실되고 있다는 뜻.
    # 반대로 raw box 자체가 낮으면 detector(모델 가중치/conf) 쪽 문제다.


def main() -> None:
    frame_idx = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    frame = _grab_frame(VIDEO_PATH, frame_idx)
    print(f"프레임 {frame_idx} 로드 완료: shape={frame.shape}")

    capdi_path = os.path.join(config.MODEL_DIR, config.YOLO_FINE_TUNED_MODEL_NAME)
    base_path = os.path.join(config.MODEL_DIR, config.YOLO_BASE_MODEL_NAME)

    # --- 1~4: 단일 프레임 시각 진단 (conf를 극단적으로 낮춰 검출 자체 여부 확인) ---
    _diagnose(
        "capdi",
        capdi_path,
        frame,
        os.path.join(OUTPUT_DIR, "diagnose_frame.jpg"),
    )
    _diagnose(
        "coco-base",
        base_path,
        frame,
        os.path.join(OUTPUT_DIR, "diagnose_frame_coco.jpg"),
    )

    # --- 5: 앞 COMPARE_FRAMES 프레임에 대해 detector vs tracker 유실 비교 ---
    fps = get_video_fps(VIDEO_PATH)
    _compare_detector_vs_tracker("capdi", Detector(), VIDEO_PATH, fps, COMPARE_FRAMES)
    _compare_detector_vs_tracker("coco-base", _RawDetector(base_path), VIDEO_PATH, fps, COMPARE_FRAMES)


if __name__ == "__main__":
    main()
