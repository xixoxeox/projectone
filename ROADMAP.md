# 개발 로드맵

## 운영 원칙

각 milestone은 작은 수직 기능으로 끝내고, 다음 단계 진입 조건을 충족해야 한다. 일정은 API 사양, 전략 규칙, 인력/예산이 확정되지 않았으므로 날짜가 아닌 결과 기준으로 관리한다.

## M0 — 설계 및 미확정 사항 해소 (현재)

**산출물**

- 요구사항/아키텍처/DB/API/배포/보안/디렉터리 설계
- 토스증권 공식 API 기능·약관·호출 한도 검증 목록
- 주문/자동매매 제외 경계
- 초기 전략과 데이터 신선도 정의를 위한 질문 목록

**Exit criteria**

- 제품 소유자가 범위, 데이터 주기, 전략 초안, AWS 예산/RPO/RTO 승인
- 핵심 ADR 후보 우선순위 결정
- 공식 API 문서와 읽기 전용 권한 확인

## M1 — 개발 기반과 인증

- Backend/Frontend scaffold(FastAPI, Next.js), PostgreSQL migration 기반
- Docker 로컬 개발 환경, 품질 도구, CI
- 설정 검증, 구조화 로그, health endpoints
- 단일 관리자 bootstrap, JWT access/rotating refresh, logout/revoke
- 모바일 shell, login, 접근성 기본

**Exit criteria:** 인증 위협 시나리오 테스트, secret scan, migration/restore 개발 검증, main CI green.

## M2 — 시장 데이터 기반

- 공급자 read-only adapter와 mock/contract test
- KOSPI 종목 마스터, 거래 캘린더, 일봉/지수 ingestion
- 멱등 job, retry/rate limit, 데이터 품질/신선도
- 운영 데이터 상태 화면

**Exit criteria:** 연속 거래일 수집 재실행 시 중복 없음, 결측/오류가 화면과 지표에 노출, 주문 scope 없음 검증.

## M3 — 시장 분석과 스크리닝 MVP

- 지표 계산 버전, 시장 국면/시장 폭
- 승인된 단일 전략의 불변 버전과 실행 파이프라인
- 결과 순위/필터/상세 rule evaluation
- 모바일 시장 대시보드와 스크리너

**Exit criteria:** 골든 데이터셋 결과 재현, stale data 신호 차단, 실행→입력→규칙 추적 가능.

## M4 — 관심 종목과 보유 종목

- watchlist/tag/note
- 수동 포트폴리오 transaction 원장과 position 파생
- 종목 상세/손익/위험 카드
- optimistic concurrency와 감사 로그

**Exit criteria:** 금액/수량 정밀도 및 정정 시나리오 테스트, 모바일 핵심 흐름 접근성/E2E 통과.

## M5 — 신호와 웹 알림

- 신호 생명주기, 무효화/만료, 중복 억제
- 알림 규칙, outbox, Web Push 구독/전송/해제
- quiet hours, rate cap, 실패/expired subscription 처리

**Exit criteria:** 동일 이벤트 중복 발송 없음, 민감 payload 없음, 사용자 동의/해제 및 폭주 중단 런북 검증.

## M6 — 백테스트

- 전략 버전/유니버스/수정주가 스냅샷
- 체결 가정, 수수료·세금·슬리피지
- look-ahead/survivorship bias 방지
- 비동기 실행, 취소, equity/trade/성과 비교 UI

**Exit criteria:** 알려진 데이터셋 회귀 테스트, 결정론적 재현, 자원 제한 아래 운영 수집 SLO 미영향.

## M7 — 운영 강화와 출시

- Lightsail production 배포, TLS/DNS, 외부 백업
- 모니터링/알림, 모든 핵심 runbook
- 부하/보안/복구 훈련, 데이터 라이선스/면책 검토
- 운영 SLO 및 비용 dashboard

**Exit criteria:** 실제 restore drill로 RPO/RTO 검증, 보안 checklist 완료, 롤백 smoke, 제품 승인.

## M8 — 측정 기반 확장(선택)

- managed PostgreSQL, Redis/전용 큐, 외부 로그/metrics
- PWA 개선, 전략 비교, 데이터 공급자 failover
- KOSDAQ 등 범위 확장은 별도 제품 결정

마이크로서비스, Kubernetes, 초단기 실시간 스트리밍은 지표와 요구가 정당화하기 전 도입하지 않는다.

## 테스트 전략

- **Unit:** 도메인 규칙, 금융 계산, 전략 평가, 시간/거래일
- **Property/golden:** OHLCV invariant, 지표/백테스트 고정 결과
- **Integration:** PostgreSQL repository/migration/job locking/outbox
- **Contract:** 공급자 mock 및 OpenAPI frontend-backend 계약
- **E2E:** 로그인, 스크리닝, 관심/포트폴리오, 알림 설정
- **Non-functional:** 모바일 접근성, 부하, 보안, 백업 복구

## Definition of Done

- 승인된 수용 기준과 자동 테스트
- 타입/lint/build/security scan 통과
- DB/API 호환성 및 migration 계획
- 데이터 기준 시각/오류/빈 상태 UI
- 로그/metric/audit와 runbook 반영
- 개인정보/비밀 미노출 검토
- 주문 또는 자동매매 기능이 포함되지 않았음
- 사용자 영향 문서와 ADR 갱신
