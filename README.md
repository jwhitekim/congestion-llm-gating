# congestion-llm-gating

저장된 실내 영상을 구간별로 분석하면서, **규칙이 고른 구간에서만 LLM을 호출하는** training-free 워크플로우입니다.

YOLOv8m과 OC-SORT로 사람을 검출·추적하고, 인원수·밀도·속도와 변화 추세를 계산합니다. 규칙이 선택한 구간의 관측값과 트리거 정보를 텍스트로 LLM에 보내 혼잡 상태와 대응 수준을 판정합니다. `action`은 대응 권고이며 실제 행동을 실행하지 않습니다.

## 결과

Mall Dataset 2,000프레임을 1 fps 영상으로 만들어 5초 단위로 분석했습니다. **400개 구간 중 101개에서만 LLM을 호출해, 매 구간 호출보다 호출 수가 74.8% 줄었습니다.**

이 수치는 호출 수만 측정한 결과입니다. 평가 조건과 한계는 [설계 원칙과 논문 실험 설정](.claude/CLAUDE.md)에 있습니다.

## 시작하기

Python 3.10 이상과 Make가 필요합니다. Git에 포함되지 않은 입력 영상 `videos/department_store.mp4`, 검출 모델 `models/yolov8m.pt`, Anthropic API 키를 준비합니다.

저장소 루트에서 기본 Anthropic 경로로 실행합니다.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install --no-deps ocsort==0.0.2
ANTHROPIC_API_KEY="<API 키>" AGENT_PROVIDER=anthropic make run
```

분석 결과의 저장 위치는 `outputs/<timestamp>/`입니다.

## 관련 문서

- [연구 결과와 한계](docs/research_findings.md)
- [설계 원칙과 논문 실험 설정](.claude/CLAUDE.md)
- [트리거 조건과 반복 호출](.claude/rules/trigger.md)
- [LLM 입력·출력 경계](.claude/rules/agent.md)
- [결과 대시보드 실행·사용법](dashboard/README.md)

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
