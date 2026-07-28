# 실내 혼잡도 모니터링 대시보드

규칙 기반 선택적 LLM 호출 워크플로우가 `outputs/<timestamp>/`에 남기는
`session.json`과 `results.jsonl`을 시각화한다. Vite 개발 서버의 미들웨어가
저장소 루트의 `outputs/`를 읽어 `/api/sessions*`로 제공하며, 브라우저는 이
API를 통해 세션 목록과 결과를 조회한다.

## 실행

```bash
npm install
npm run dev
```

브라우저에서 안내된 주소를 연다.

## 실행 제약

세션 API는 Vite 개발 서버의 `configureServer` 미들웨어에 구현돼 있다.
`npm run build`로 생성한 정적 파일만 배포하거나 `vite preview`로 실행하면
세션 API가 없어 목록을 불러올 수 없다.

## 사용법

1. 워크플로우를 실행해 저장소 루트의 `outputs/`에 세션 결과를 생성한다.
2. 대시보드의 세션 목록에서 원하는 세션을 선택한다.
3. 상세 화면에서 LLM 호출 수, 시계열, latency, 세그먼트 결과를 확인한다.
4. 선택한 세션이 실행 중이면 1초 간격으로 자동 갱신하며, 세션 종료 후 갱신을 멈춘다.

브라우저는 세션 데이터를 localStorage에 저장하지 않는다.
