import numpy as np
import torch
from ocsort.ocsort import OCSort


class Tracker:
    """OC-SORT 래퍼. track ID 안정화만 담당."""

    def __init__(self, frame_rate: float = 30.0, det_thresh: float = 0.3):
        # frame_rate는 OC-SORT가 안 쓰지만, pipeline.py 호출부(Tracker(frame_rate=fps))와
        # 인터페이스 호환을 위해 인자는 유지한다.
        #
        # det_thresh=0.3, max_age=50, min_hits=1: 선행 시스템 레포
        # (jwhitekim/indoor-congestion-analysis,
        # backend/videostream/manager/video_processor.py 27번째 줄)의 설정을 재현성
        # 목적으로 유지한다. 현재 논문이 이 하이퍼파라미터의 최적성을 별도로
        # 검증했다는 뜻은 아니다.
        #
        # det_thresh=0.3은 config.py의 detector conf(0.07)보다 훨씬 높다. 이 둘은
        # 서로 다른 역할이다 — detector 단계(0.07)는 "일단 넓게 잡고", tracker
        # 단계(0.3)는 그중 무엇을 신뢰할지 다시 거른다. use_byte=True이므로 conf
        # 0.1~0.3 사이 detection은 새 트랙을 시작하진 못해도(새 트랙은 여전히
        # conf > 0.3만) 기존 트랙과의 2차 매칭(BYTE association)에는 쓰인다 —
        # conf 0.1 이하만 두 라운드 모두에서 완전히 버려진다(ocsort 패키지
        # OCSort.update()의 inds_low = confs > 0.1 기준).
        #
        # asso_func="ct_dist": 원 레포엔 명시돼 있지 않다(기본값 "iou"로 추정되나
        # 원 레포에서 직접 확인은 못 함) — 이 판단은 원래 capdi(config.py의
        # YOLO_FINE_TUNED_MODEL_NAME, head 검출기) 기준으로 내려졌다: head 박스가
        # 작아 IoU 매칭이 구조적으로 실패하는 문제(ByteTrack에서도 동일 현상 재현,
        # scripts/diagnose_detector.py로 검증) 때문에 우리 쪽 판단으로 유지했다.
        # 지금 기본값(config.YOLO_MODEL_CHOICE="base")은 COCO 전신 검출이라 박스가
        # 훨씬 커서 그 문제 자체는 기본 경로엔 해당하지 않지만, capdi도 여전히
        # YOLO_MODEL_CHOICE=fine_tuned로 선택 가능하고 두 모델 다 같은 Tracker를
        # 거치므로 한쪽 모델에만 맞춰 값을 바꾸지 않았다. 원 알고리즘 대비 변경한
        # 지점이므로 논문에 그렇게 밝혀야 한다. density 계산(perception/density.py의
        # calc_spatial_density, pipeline.py의 zone 계산)도 bbox 중심점만 쓰므로
        # 매칭 기준을 중심점으로 맞추는 것이 그 설계와 일관된 선택이기도 하다 —
        # 이쪽은 검출기 종류(head/전신)와 무관하게 여전히 유효하다.
        self._tracker = OCSort(
            det_thresh=det_thresh, max_age=50, min_hits=1, asso_func="ct_dist", use_byte=True
        )

    def update(self, detections: torch.Tensor) -> list:
        """
        Returns list of [x1, y1, x2, y2, track_id, score] arrays for confirmed tracks.
        Empty list when no detections.
        OCSort.update()은 [x1,y1,x2,y2,conf,cls] 텐서를 그대로 받고
        (detector.py 출력 포맷과 동일, 변환 불필요),
        [x1,y1,x2,y2,track_id,cls,conf] 7열을 반환한다 — 여기서 track_id(4번 인덱스)와
        conf(6번 인덱스)만 뽑아 기존 6열 포맷([x1,y1,x2,y2,track_id,score])으로 맞춘다.
        """
        if len(detections) == 0:
            detections = torch.zeros((0, 6), dtype=torch.float32)

        tracked = self._tracker.update(detections, None)

        rows = []
        for row in tracked:
            x1, y1, x2, y2, track_id, cls, score = row
            rows.append([float(x1), float(y1), float(x2), float(y2), int(track_id), float(score)])
        return rows
