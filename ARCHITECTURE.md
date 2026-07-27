# 시스템 아키텍처

## 1. 아키텍처 개요

초기 시스템은 **Next.js 프론트엔드 + FastAPI 백엔드 + SQLAlchemy + PostgreSQL**로 구성한 모듈러 모놀리스다. 웹/API와 장기 작업 워커는 같은 백엔드 코드베이스의 서로 다른 실행 역할로 분리한다. Docker 컨테이너로 패키징하되 본 설계 단계에서는 Dockerfile이나 Compose 파일을 만들지 않는다.

```text
Mobile Browser
  └─ HTTPS
     └─ Reverse Proxy (TLS, security headers, rate limit)
        ├─ Next.js Web (SSR/BFF 최소화)
        └─ FastAPI /api/v1
             ├─ Auth / Users
             ├─ Market Data / Universe
             ├─ Screening / Signals
             ├─ Watchlist / Portfolio
             ├─ Notifications
             ├─ Backtests
             └─ Operations
                  ├─ SQLAlchemy → PostgreSQL
                  ├─ Job Worker/Scheduler → PostgreSQL queue (초기안)
                  └─ Toss Securities read-only adapter
```

## 2. 컨테이너/프로세스 책임

| 구성 요소 | 책임 | 상태 |
|---|---|---|
| Reverse proxy | TLS 종료, 라우팅, 압축, 보안 헤더, 요청 크기 제한 | 인증 상태 없음 |
| Next.js | 모바일 UI, 서버/클라이언트 렌더링, API 소비 | 영속 상태 없음 |
| FastAPI API | 인증, 입력 검증, 유스케이스, 조회 API | 영속 상태 없음 |
| Worker | 수집, 지표/신호 계산, 알림, 백테스트 | DB에 실행 상태 저장 |
| Scheduler | 거래 캘린더 기반 작업 등록 | 리더 1개, 중복 등록 방지 |
| PostgreSQL | 업무 데이터, 작업 큐, 감사/실행 이력 | 영속 볼륨/백업 |

초기에는 API/worker/scheduler가 동일 이미지와 코드를 공유할 수 있지만 프로세스는 분리한다. Redis는 필수 구성으로 시작하지 않는다. 작업량과 지연 지표가 PostgreSQL 큐의 한계를 증명할 때 Redis를 추가해 운영 복잡도를 정당화한다.

## 3. Backend 구조

### 계층

1. **Presentation:** FastAPI router, Pydantic request/response, 인증 dependency
2. **Application:** 유스케이스, 트랜잭션 경계, 권한/정책 조정
3. **Domain:** 엔티티 의미, 값 객체, 전략 규칙 인터페이스, 도메인 오류
4. **Infrastructure:** SQLAlchemy repository, 외부 API adapter, JWT/암호화, 알림 adapter

라우터는 SQLAlchemy 모델을 직접 반환하지 않고 API 스키마로 변환한다. 공급자 DTO도 도메인/DB 모델과 분리한다.

### Backend 도메인 모듈

- `identity`: 관리자, 자격 증명, refresh session
- `market`: 종목, 거래 캘린더, OHLCV, 지수, 시장 상태
- `screening`: 전략 정의/버전, 실행, 종목별 평가 근거
- `signals`: 매수 후보/위험/청산 조건과 생명주기
- `watchlists`: 관심 목록, 태그, 메모
- `portfolio`: 보유 종목, 수동 거래, 성과 계산
- `notifications`: 구독, 규칙, delivery/outbox
- `backtesting`: 실행 정의, 체결 가정, 결과/지표
- `operations`: 작업, 데이터 품질, 감사 로그, 상태 점검

### 트랜잭션과 작업

- HTTP 쓰기 유스케이스 하나를 기본 트랜잭션 경계로 한다.
- 외부 API 호출 중 DB 트랜잭션을 오래 유지하지 않는다.
- 원본 수신 → 검증/정규화 → staging 또는 메모리 변환 → 짧은 upsert 순으로 처리한다.
- 비동기 요청은 `202 Accepted`와 `job_id`를 반환하고 상태를 폴링한다.
- 알림은 동일 트랜잭션에서 outbox에 기록하고 worker가 전달해 유실을 줄인다.

## 4. 데이터 파이프라인

```text
Scheduler
 → ingestion job 생성(멱등 키)
 → 공급자 호출(재시도/백오프/호출 제한)
 → 스키마·범위·중복·거래일 검증
 → 정규화/저장(raw payload는 정책에 따라 제한 보존)
 → technical indicator 계산
 → market regime 계산
 → strategy version별 screening
 → signal 생성/변경
 → notification outbox 생성
 → web push 전달
```

각 단계는 `job_runs`에 입력 기준 시각, 코드/전략 버전, 처리 건수, 오류 요약을 남긴다. 선행 작업 실패 시 후속 신호를 생성하지 않는다.

## 5. Frontend 구조

Next.js는 App Router 기준으로 설계하되 실제 버전은 구현 시작 시 지원 정책을 확인해 고정한다.

### 화면 정보 구조

- `/login`: 관리자 로그인
- `/`: 오늘의 시장, 데이터 상태, 핵심 후보/위험
- `/screeners`: 프리셋/실행 결과/필터
- `/stocks/[symbol]`: 차트, 지표, 신호 근거, 관심/보유 행동
- `/watchlists`: 관심 목록, 태그, 메모
- `/portfolio`: 보유 현황, 손익, 위험/청산 후보
- `/alerts`: 알림 피드/규칙/푸시 구독
- `/backtests`: 실행 생성, 상태, 결과 비교
- `/settings`: 데이터/전략/계정/운영 상태

### 상태 관리 원칙

- 서버 데이터: 요청 캐시와 재검증이 가능한 전용 query 계층 사용
- URL 상태: 스크리너 필터, 정렬, 페이지, 선택 프리셋
- 로컬 UI 상태: 모달, 펼침, 임시 입력에 한정
- 인증 토큰: 접근 토큰을 JavaScript 영속 저장소에 두지 않는 방식을 우선
- 숫자/시간: API 원문과 표시 포맷을 분리하고 KST 기준 시각을 명시

### 디자인 원칙

하단 내비게이션은 4~5개 핵심 메뉴로 제한하고, 표를 좁은 화면에서 강제하지 않는다. 상승/하락을 색상만으로 구분하지 않으며 아이콘·부호·텍스트를 병행한다. 모든 신호 카드에는 `데이터 기준`, `전략 버전`, `근거`, `무효/주의 조건`을 제공한다.

## 6. 신호 및 스크리닝 모델

전략은 불변 `strategy_version`으로 관리한다. 실행 결과에는 다음을 저장한다.

- 대상 거래일과 데이터 `as_of`
- 유니버스 스냅샷/제외 정책
- 규칙별 입력값, 비교 연산, 임계값, 통과 여부
- 가중치와 최종 점수/순위
- 코드 버전, 전략 버전, 실행 ID

“매수/매도 타이밍”은 주문 지시가 아니라 **관찰 신호**다. 오래된 데이터, 결측치, 거래정지, 유동성 기준 미달 시 신호를 차단하고 사유를 노출한다.

## 7. 캐시 및 성능

- 정적 종목 메타데이터와 최신 시장 요약은 짧은 TTL 응답 캐시 후보
- 스크리닝 결과는 실행 단위로 물리화해 매 요청 재계산하지 않음
- OHLCV는 `(instrument_id, trading_date)` 복합 키와 날짜 기반 파티셔닝을 데이터 규모 측정 후 검토
- 목록은 cursor pagination을 우선하고 안정적인 tie-breaker를 포함
- 차트 데이터는 요청 기간/해상도를 제한
- 백테스트는 사용자별(현재 1명) 동시 실행 1개와 자원 한도를 초기 정책으로 제안

## 8. 장애 처리와 관측성

- 모든 요청에 `X-Request-ID`; job에는 correlation ID
- JSON 로그에 비밀, JWT, 전체 외부 응답, 민감 헤더를 남기지 않음
- 외부 API 오류는 timeout, rate limit, auth, validation, provider outage로 분류
- 재시도는 일시 오류에만 지수 백오프+jitter 적용, 최대 횟수 후 dead-letter 상태
- `/health/live`는 프로세스 생존, `/health/ready`는 필수 의존성 준비 여부(외부 공급자 장애는 별도 degraded 상태)
- 지표: API latency/error, DB pool, queue depth/age, job duration/failure, data freshness, notification failure

## 9. 대안과 장단점

| 결정 | 선택 이유 | 단점/전환 조건 |
|---|---|---|
| 모듈러 모놀리스 | 팀/운영 규모에 단순, 트랜잭션 쉬움 | 배포 독립성 낮음; 작업 부하가 커지면 worker 서비스 분리 |
| PostgreSQL 단일 데이터 저장소 | 관계/시계열/JSON 요구를 초기 규모에서 수용 | 초대형 시계열에 비효율; 보존량 측정 후 Timescale/객체 저장소 검토 |
| DB 기반 큐 초기안 | Redis 운영 비용 제거, 내구성 | 높은 처리량/정밀 스케줄 한계; queue age 목표 위반 시 Redis 검토 |
| JWT access + 회전 refresh | API 확장성, 세션 폐기 균형 | 구현 복잡; 단일 사용자라도 CSRF/XSS 방어 필요 |
| REST `/api/v1` | 도메인과 클라이언트가 단순 | 복합 대시보드 over-fetch; 전용 summary endpoint로 보완 |

## 10. 아키텍처 제약

- 주문 기능으로 이어지는 port/interface를 정의하지 않는다.
- API/워커 인스턴스 로컬 디스크를 영속 저장소로 사용하지 않는다.
- 공급자 API가 불명확한 필드는 추정 매핑하지 않는다.
- 금융 계산은 부동소수점 대신 적절한 `NUMERIC`/Decimal을 사용한다.
- 운영자가 수정 가능한 전략과 배포 코드 전략의 범위를 구현 전에 확정한다.
