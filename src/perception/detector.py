import os
import torch
from ultralytics import YOLO
import config


class Detector:
    """YOLO 추론만 담당. 판단 없음."""

    def __init__(self):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        model_path = os.path.join(config.ACTIVE_MODEL_DIR, config.ACTIVE_YOLO_MODEL)
        self._model = YOLO(model_path).to(self.device)

    def detect(self, frame, conf: float = 0.07) -> torch.Tensor:
        """
        Returns float32 tensor of shape (N, 6): [x1, y1, x2, y2, conf, cls].
        Empty tensor (0, 6) when nothing detected.
        """
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
