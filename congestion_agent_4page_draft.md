# 실내 혼잡도 모니터링을 위한 규칙 기반 선택적 LLM 호출: 호출 절감과 LLM 판정 분포 분석

**Rule-Gated Selective LLM Invocation for Indoor Congestion Monitoring: Call Reduction and LLM Output Analysis**

> 작성 메모: 공개 데이터셋 재실행 후 `<데이터셋명>`, `<세그먼트 수>`, `<호출 수>`, `<감소율>`, `<출력 분포>`를 교체한다. 아래 결과 수치는 기존 실험값을 임시로 유지한 것이다.

## 초록

실내 영상 기반 혼잡도 모니터링에서는 객체 검출과 추적을 통해 인원수, 밀도 및 이동 정보를 지속적으로 계산할 수 있다. 그러나 모든 영상 구간에서 대규모 언어 모델(LLM)을 호출하면 정상 구간에도 비용과 지연이 누적되며, 반대로 고정 규칙만으로 최종 상태를 결정하면 여러 관측 신호가 함께 나타나거나 상충하는 상황을 단일 임계값으로 처리해야 한다. 본 연구는 영상 인지와 상황 판단을 분리하고, 규칙 기반 혼잡 이벤트가 감지된 구간에서만 LLM을 호출하는 training-free 워크플로우를 제안한다. 시스템은 YOLO 기반 사람 검출, OC-SORT 기반 추적 및 구역별 밀도·속도 통계를 매 구간 계산한 뒤, 밀도 급증, 이동 정체, 국소 집중 및 상태–추세 불일치가 발생할 때 구조화된 텍스트 관측값을 LLM에 전달한다. 기존 실험에서 전체 399개 구간 중 101개에서만 LLM을 호출하여 always-call 대비 호출량을 74.7% 줄였고, 선택된 구간에서는 LLM의 비정상 출력 비율이 높게 나타났다. 한편 미선택 구간에서도 비정상 출력이 존재하여, 선택적 호출 시스템은 호출 감소뿐 아니라 선택·미선택 구간의 출력 분포를 함께 분석해야 함을 확인하였다.

**주요어:** 실내 혼잡도, 선택적 LLM 호출, 이벤트 트리거, 객체 추적, 모니터링 시스템

---

## 1. 서론

실내 혼잡도 모니터링은 건물 내부의 인원수와 위치, 이동 상태를 지속적으로 관측하고 공간의 혼잡 수준과 대응 필요성을 판단하는 과정이다. 이러한 정보는 냉난방·환기와 조명 제어, 리테일 공간 운영, 공공시설 안전관리 및 비상 대응 등에 활용될 수 있다[1,2]. 특히 동일한 인원수라도 사람이 한 구역에 집중되거나 이동 흐름이 정체되면 서로 다른 혼잡 상태가 형성되므로, 전체 인원수뿐 아니라 공간적 분포와 시간적 변화가 함께 고려되어야 한다.

최근 객체 검출과 다중 객체 추적 기술의 발전으로 사람의 위치, 궤적, 구역별 인원수와 속도를 실시간으로 계산할 수 있게 되었다. 그러나 이러한 관측값을 실제 혼잡 상태와 대응 수준으로 변환하는 과정은 여전히 설계자의 규칙과 임계값에 크게 의존한다. 또한 LLM을 이용해 여러 관측 신호를 종합적으로 해석할 수 있지만, 연속 영상의 모든 구간에서 LLM을 호출하면 정상 구간에도 반복적인 비용과 응답 지연이 발생한다.

이에 본 연구는 코드 기반 인지 계층이 모든 구간의 관측값을 계산하고, 규칙 기반 이벤트가 발생한 구간에서만 텍스트 LLM을 호출하는 선택적 호출 구조를 제안한다. LLM은 영상을 직접 분석하거나 수치를 생성하지 않고, 코드가 계산한 구역별 밀도, 속도 및 변화 추세를 바탕으로 혼잡 상태와 대응 수준을 단발성으로 판정한다. 본 연구는 제안 구조를 always-call 방식과 비교하여 호출 감소 효과를 측정하고, 선택된 구간과 선택되지 않은 구간의 LLM 출력 분포를 함께 분석한다.

본 연구의 기여는 다음과 같다. 첫째, 영상 인지와 LLM 판단을 분리한 rule-gated LLM 워크플로우를 설계하였다. 둘째, 도메인 혼잡 이벤트를 이용해 LLM 호출 시점을 결정하고 always-call 대비 호출 감소를 실측하였다. 셋째, 선택·미선택 구간의 출력 분포를 비교하여 현재 게이트의 선택 특성과 한계를 분석하였다.

---

## 2. 관련 연구

실내 점유 및 혼잡도 추정은 센서 기반 방식과 영상 기반 방식으로 구분할 수 있다. 센서 기반 방법은 PIR, CO₂, WiFi 및 Bluetooth 신호를 이용하여 사람의 존재나 인원수를 간접적으로 추정한다[1,2]. 영상 기반 방법은 사람을 개별적으로 검출하고 추적하는 방식과 픽셀별 군중 밀도를 회귀하는 방식으로 나뉜다. YOLO 계열 검출기와 ByteTrack·OC-SORT 등의 추적기는 구역별 인원수와 이동 궤적을 계산할 수 있으나, 가림과 낮은 검출 신뢰도에 따른 객체 누락 및 궤적 단절 문제가 존재한다[3-5]. MCNN과 CSRNet은 고밀도 장면의 밀도맵을 추정하지만 학습용 점 주석이 필요하고 개별 객체의 궤적을 직접 제공하기 어렵다[6,7]. 또한 카메라 원근으로 영상 내 사람의 크기가 위치마다 달라지므로 장면 간 또는 구역 간 밀도 비교에는 원근 보정이 요구된다[8].

군중의 혼잡과 위험은 단일 인원수나 밀도 값만으로 충분히 설명되지 않는다. 동일한 밀도에서도 이동 방향과 흐름 구조에 따라 군중 위험이 달라질 수 있으며, 밀도와 유량이 일정한 상황에서도 서로 다른 조직 구조가 형성될 수 있다[9]. 따라서 국소 집중, 단기 급증, 이동 정체 및 현재 상태와 변화 추세의 불일치를 함께 고려할 필요가 있다.

LLM의 계산 비용을 줄이기 위한 연구로는 모델 라우팅과 캐스케이드가 있으며, FrugalGPT는 여러 LLM을 비용과 성능에 따라 순차적으로 사용하는 방식을 제안하였다[10]. StreamMind는 스트리밍 영상에서 학습된 게이트가 관련 이벤트에만 LLM을 활성화하였다[11]. 실내 점유 분야에서는 낮은 검출 신뢰도나 급격한 인원수 변화가 나타난 프레임만 텍스트 LLM으로 보정하는 연구가 보고되었다[12]. 그러나 해당 연구는 점유 인원수 보정이 주목적이며, 구역별 시공간 관측값을 이용해 혼잡 상태를 판정하고 선택·미선택 구간의 출력 특성을 분석하는 본 연구와 차이가 있다.

---

## 3. 이벤트 트리거 기반 LLM 호출 방법

제안 시스템은 Perception, Rule-Based Trigger, LLM Assessment의 세 단계로 구성된다. Perception은 모든 영상 구간에서 YOLO 기반 사람 검출, OC-SORT 기반 추적, 전체·구역별 인원수, 밀도, 평균 속도 및 밀도 변화율을 계산한다. Trigger는 현재 관측값과 최근 이력을 이용해 혼잡 이벤트 조건을 검사한다. 이벤트가 없으면 관측값만 기록하고 종료하며, 이벤트가 발생하면 구조화된 텍스트 관측값을 LLM에 전달한다.

> **[그림 1]** 영상 스트림 → 사람 검출·추적 → 구역별 통계 → 규칙 기반 이벤트 게이트 → 선택적 LLM 단발 판정

시스템의 설계 원칙은 `perception = observations, LLM = judgment`이다. 인원수, 밀도, 속도와 구역 분포는 코드가 계산하며, LLM은 영상을 직접 보거나 외부 도구를 호출하지 않는다. 호출 여부와 실행 경로 역시 규칙 기반 코드가 결정한다.

**표 1. 규칙 기반 혼잡 이벤트**

| 트리거 | 조건 | 감지 대상 |
|---|---|---|
| surge | density > 최근 평균 × 1.4 | 상대적 밀도 급증 |
| stagnation | 평균 속도 < 0.5가 10초 이상 지속 | 이동 정체 |
| hotspot | 구역 인원 > percentile 기반 임계값 | 국소 인원 집중 |
| conflict | level=low, density slope > 0.4 | 상태–추세 불일치 |

LLM에는 세그먼트 시각, 전체·구역별 인원수, 밀도, 평균 속도, 밀도 변화율, 혼잡 수준과 트리거 정보를 제공한다. 출력은 `assessment ∈ {normal, caution, anomaly}`와 `action ∈ {none, monitor, alert}`이다. 게이트와 LLM의 추가 학습은 수행하지 않는다. 현재 규칙에는 전역 절대 고밀도의 지속을 직접 감지하는 조건이 포함되지 않는다.

---

## 4. 실험 및 결과

실험에는 연구 목적으로 공개된 연속 실내 영상 데이터셋 `<데이터셋명>`을 사용한다. 영상을 `<간격>`초 단위로 나누어 총 `<N>`개 구간을 구성하고, 검출에는 YOLOv8m, 추적에는 OC-SORT를 적용한다. 제안 방식은 규칙이 선택한 구간에만 LLM을 호출하며, always-call 비교에서는 동일한 perception 결과를 사용해 전체 구간을 평가한다. 최종 원고에는 데이터셋의 공식 출처, 영상 길이, 해상도, LLM 모델명, temperature 및 프롬프트 버전을 기재한다.

기존 실험에서는 전체 399개 구간 중 101개가 규칙에 의해 선택되고 298개는 선택되지 않았다. 제안 방식은 always-call 대비 호출량을 74.7% 줄였다. 선택된 구간과 미선택 구간을 모두 강제 평가한 출력 분포는 표 2와 같다.

**표 2. 규칙 선택 여부에 따른 LLM 출력 분포 — 기존 실험값, 공개 데이터셋 재실행 후 교체**

| 구분 | caution+anomaly | normal | 합계 |
|---|---:|---:|---:|
| 규칙 트리거 | 100 | 1 | 101 |
| 규칙 미트리거 | 107 | 191 | 298 |
| 합계 | 207 | 192 | 399 |

선택된 101개 구간 중 100개에서 LLM은 `caution/anomaly`를 출력하여 선택 호출 비정상 출력률은 99.0%였다. 미선택 구간을 강제로 평가했을 때 191개, 즉 64.1%는 `normal/none`으로 종료되었다. 이는 현재 게이트가 정상 판정으로 끝날 호출을 상당수 줄이고, LLM 비정상 출력 비율이 높은 구간에 호출을 집중시키는 성질을 보였음을 의미한다.

반면 미선택 구간의 107개에서도 `caution/anomaly`가 출력되었다. 따라서 게이트가 객관적으로 불필요한 호출만 제거하거나 필요한 호출을 모두 보존했다고 주장할 수 없다. 전체 LLM 비정상 출력 207개 중 게이트가 선택한 비율은 48.3%였으나, 객관적 위험 라벨이 없고 트리거 구간과 미트리거 구간의 프롬프트 정보가 대칭적이지 않으므로 이를 실제 이상 탐지 recall로 해석하지 않는다.

사례 분석에서 surge와 hotspot은 각각 전역 밀도의 급격한 증가와 특정 구역의 인원 집중을 선택하였고, conflict는 현재 혼잡 수준이 낮지만 밀도 변화율이 큰 구간에서 `caution/monitor` 판정을 유도하였다. 이는 LLM이 규칙보다 정확하다는 증거가 아니라, 서로 다른 관측 신호를 종합하도록 정의한 판정 정책이 출력에 반영된 사례이다. 또한 미선택 anomaly 출력은 지속적인 고밀도 구간에 집중되어, 현재 규칙 집합에 전역 절대 고밀도 지속 조건이 부족할 가능성을 보여주었다.

---

## 5. 결론 및 한계

본 연구는 실내 혼잡도 모니터링에서 코드 기반 인지 계층이 관측값을 지속적으로 계산하고, 규칙이 선택한 구간에만 텍스트 LLM을 호출하는 training-free 워크플로우를 제안하였다. 기존 실험에서는 always-call 대비 LLM 호출량을 74.7% 줄였으며, 선택된 구간에서 LLM의 비정상 출력 비율이 높게 나타났다. 동시에 미선택 구간에서도 비정상 출력이 확인되어, 선택적 호출의 효과는 호출 감소율만이 아니라 선택·미선택 구간의 출력 분포를 함께 고려해 해석해야 함을 보였다. 본 연구의 의의는 혼잡도 추정 모델의 정확도를 개선한 데 있지 않고, 연속 모니터링에서 LLM 호출 시점을 독립적인 시스템 설계 문제로 구성하고 그 선택 특성을 분석한 데 있다.

본 연구는 객관적 혼잡 정답 라벨이 없고, 트리거 구간과 미트리거 구간의 프롬프트 정보가 대칭적이지 않으며, 단일 영상과 단순한 화면 3분할 구역을 사용했다는 한계가 있다. 또한 실제 바닥 면적과 원근을 반영하지 않았고 전역 절대 고밀도 지속 규칙이 포함되지 않았다. 향후에는 공개 데이터셋과 고정된 perception 결과를 사용하고, 트리거 정보를 제거한 블라인드 프롬프트에서 random, periodic 및 fixed-threshold 게이트와 비교할 필요가 있다.

---

## 참고문헌

[1] H. Saha, A. R. Florita, G. P. Henze, and S. Sarkar, “Occupancy sensing in buildings: A review of data analytics approaches,” *Energy and Buildings*, vols. 188–189, pp. 278–285, 2019.

[2] Z. Chen, C. Jiang, and L. Xie, “Building occupancy estimation and detection: A review,” *Energy and Buildings*, vol. 169, pp. 260–270, 2018.

[3] J. Redmon, S. Divvala, R. Girshick, and A. Farhadi, “You Only Look Once: Unified, Real-Time Object Detection,” in *Proc. CVPR*, pp. 779–788, 2016.

[4] Y. Zhang et al., “ByteTrack: Multi-Object Tracking by Associating Every Detection Box,” in *Proc. ECCV*, 2022.

[5] J. Cao, J. Pang, X. Weng, R. Khirodkar, and K. Kitani, “Observation-Centric SORT: Rethinking SORT for Robust Multi-Object Tracking,” in *Proc. CVPR*, pp. 9686–9696, 2023.

[6] Y. Zhang, D. Zhou, S. Chen, S. Gao, and Y. Ma, “Single-Image Crowd Counting via Multi-Column Convolutional Neural Network,” in *Proc. CVPR*, pp. 589–597, 2016.

[7] Y. Li, X. Zhang, and D. Chen, “CSRNet: Dilated Convolutional Neural Networks for Understanding the Highly Congested Scenes,” in *Proc. CVPR*, pp. 1091–1100, 2018.

[8] M. Shi, Z. Yang, C. Xu, and Q. Chen, “Revisiting Perspective Information for Efficient Crowd Counting,” in *Proc. CVPR*, pp. 7279–7288, 2019.

[9] C. Feliciani and K. Nishinari, “Measurement of congestion and intrinsic risk in pedestrian crowds,” *Transportation Research Part C: Emerging Technologies*, vol. 91, pp. 124–155, 2018.

[10] L. Chen, M. Zaharia, and J. Zou, “FrugalGPT: How to Use Large Language Models While Reducing Cost and Improving Performance,” *Transactions on Machine Learning Research*, 2024.

[11] X. Ding et al., “StreamMind: Unlocking Full Frame Rate Streaming Video Dialogue through Event-Gated Cognition,” in *Proc. ICCV*, pp. 13448–13459, 2025.

[12] I. Qaisar, K. Sun, Q. Jia, and Q. Zhao, “Experimental Study on Surveillance Video-Based Indoor Occupancy Measurement with Occupant-Centric Control,” arXiv:2603.26081, 2026.
