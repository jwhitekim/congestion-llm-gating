# congestion-llm-gating

저장된 실내 영상을 구간별로 분석하면서, **규칙이 고른 구간에서만 LLM을 호출하는** training-free 워크플로우입니다.

YOLOv8m과 OC-SORT로 사람을 검출·추적하고, 모든 구간에서 인원수·밀도·속도와 그 추세를 계산합니다. 밀도 급증, 이동 정체, 국소 집중, 상태와 추세의 불일치가 보이면 그 구간의 관측값과 트리거 정보를 텍스트로 LLM에 보냅니다. LLM은 혼잡 상태와 대응 수준을 판정합니다. `action`은 권고일 뿐 실제로 실행하지 않습니다.

## 결과

Mall Dataset 2,000프레임을 1 fps 영상으로 만들어 5초 단위로 분석했습니다. **400개 구간 중 101개에서만 LLM을 호출해, 매 구간 호출보다 호출 수가 74.8% 줄었습니다.**

- 줄어든 것은 호출 수입니다. 비용·토큰·지연 감소나 혼잡 탐지 정확도를 측정한 것은 아닙니다.
- 매 구간 호출로 판정했을 때, 규칙이 고르지 않은 구간에서도 `caution/anomaly`가 105개 나왔습니다.
- 혼잡 정답 라벨이 없고, LLM에 전달한 트리거 정보가 판정에 영향을 줄 수 있습니다.

## 시작하기

저장소 루트에서 실행합니다. 의존성은 [`requirements.txt`](requirements.txt)에 있고, PyTorch는 CUDA 12.6 빌드입니다.

> [!WARNING]
> `requirements.txt`의 `lapx --break-system-packages` 줄은 pip가 읽지 못합니다. 코드가 쓰는 `python-dotenv`도 목록에 없습니다.

실행 전에 준비할 것은 다음과 같습니다. 영상과 모델 파일은 Git에 포함되지 않습니다.

| 항목 | 기본값 |
| --- | --- |
| 입력 영상 | `videos/department_store.mp4` |
| 검출 모델 | `models/yolov8m.pt` |
| API 키 | `ANTHROPIC_API_KEY` (Gemini는 `AGENT_PROVIDER=gemini`, `GEMINI_API_KEY`) |

```bash
make run
make run VIDEO=videos/supermarket.mp4   # 다른 영상
```

결과는 `outputs/<timestamp>/`의 `session.json`(세션 정보)과 `results.jsonl`(구간별 관측값·판정)에 저장됩니다. LLM을 부르지 않은 구간은 `agent: null`입니다. 결과는 [대시보드](dashboard/README.md)로 볼 수 있습니다.

모델과 임계값은 [`src/config.py`](src/config.py)에 있습니다. 현재 기본값은 논문 실험 설정(`gemini-3.1-flash-lite`, temperature 0)과 다릅니다.

## 관련 문서

- [설계 원칙, 논문과 현재 구현의 차이](.claude/CLAUDE.md)
- [트리거 조건과 반복 호출](.claude/rules/trigger.md)
- [LLM 입력·출력 경계](.claude/rules/agent.md)

## 인용

혼잡도 분석 파이프라인(검출·추적, Line Density)은 아래 논문의 시스템을 바탕으로 합니다.

```bibtex
@inproceedings{kim2026realtime,
  author    = {Kim, Jun-Hee and Lee, Sang-Woong},
  title     = {Real-time Indoor Congestion Analysis System Using Head Detection and Line Density Analysis},
  booktitle = {Proc. of 2026 KING Spring Conference},
  address   = {Gwangju, Korea},
  month     = may,
  year      = {2026},
  pages     = {224--227}
}
```

## 라이선스

LICENSE 파일이 없습니다. 라이선스는 확인이 필요합니다.
