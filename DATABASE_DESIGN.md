# 데이터베이스 설계

## 1. 원칙

PostgreSQL을 단일 원천 데이터베이스로 사용하고 SQLAlchemy 2.x 스타일 ORM 및 명시적 migration 도구를 사용할 예정이다. 구체 버전은 구현 시 고정한다. 모든 테이블은 기본적으로 `created_at`, 필요한 경우 `updated_at`을 UTC `timestamptz`로 가진다.

- 내부 PK: `bigint` 또는 UUID 중 모듈별 일관된 규칙(외부 노출 ID는 UUID 권장)
- 가격/수량/비율: `numeric`, 금액 단위와 반올림 규칙 명시
- 거래일: `date`, 이벤트 시각: `timestamptz`
- 심볼 문자열을 FK처럼 사용하지 않고 `instrument_id` 참조
- 삭제는 감사 필요 도메인에서 상태/시각 기반 soft delete, 나머지는 명시적 hard delete
- JSONB는 공급자 부가 필드/규칙 스냅샷에 제한하고 핵심 조회 필드는 정규화

## 2. 핵심 관계

```text
users 1─N refresh_sessions
instruments 1─N daily_bars
instruments 1─N watchlist_items N─1 watchlists
instruments 1─N positions 1─N portfolio_transactions
strategy_definitions 1─N strategy_versions 1─N screening_runs
screening_runs 1─N screening_results N─1 instruments
screening_results 1─N rule_evaluations
instruments 1─N signals N─1 strategy_versions
users 1─N push_subscriptions
notification_rules 1─N notification_deliveries
backtest_runs 1─N backtest_trades
job_runs 1─N job_events
```

## 3. 테이블 카탈로그

### 인증/감사

| 테이블 | 주요 컬럼 | 제약/설명 |
|---|---|---|
| `users` | id, username, password_hash, role, is_active, last_login_at | username unique; 초기 관리자 1명은 배포 절차로 생성 |
| `refresh_sessions` | id, user_id, token_hash, family_id, expires_at, revoked_at, replaced_by_id, user_agent_hash | 원문 토큰 저장 금지; 회전/재사용 탐지 |
| `audit_logs` | id, actor_user_id, action, resource_type, resource_id, request_id, metadata, occurred_at | append-only; 비밀/토큰 제외 |

### 시장 데이터

| 테이블 | 주요 컬럼 | 제약/설명 |
|---|---|---|
| `instruments` | id, symbol, name_ko, market, sector_code, listed_on, delisted_on, status | `(market, symbol)` unique; 과거 종목 유지 |
| `instrument_status_history` | id, instrument_id, status, effective_from, effective_to, reason | 거래정지/관리 상태 시점 추적 |
| `trading_calendar` | market, trading_date, is_open, session_open_at, session_close_at | `(market, trading_date)` PK |
| `daily_bars` | instrument_id, trading_date, open, high, low, close, adjusted_close, volume, trading_value, source, ingested_at | `(instrument_id, trading_date, source)` unique; OHLC 범위 check |
| `corporate_actions` | id, instrument_id, action_type, ex_date, ratio, cash_amount, source | 수정주가 재현 근거 |
| `market_indices` | id, code, name | code unique |
| `index_daily_bars` | index_id, trading_date, OHLCV, source | `(index_id, trading_date, source)` unique |
| `market_snapshots` | id, trading_date, as_of, regime, breadth metrics, trading_value, calculation_version | 거래일/버전별 시장 분석 |
| `data_quality_issues` | id, dataset, business_key, severity, rule_code, details, detected_at, resolved_at | 결측/범위/중복 추적 |

### 전략/스크리닝/신호

| 테이블 | 주요 컬럼 | 제약/설명 |
|---|---|---|
| `strategy_definitions` | id, key, name, description, strategy_type, is_active | key unique |
| `strategy_versions` | id, strategy_id, version, parameters, rules, code_version, published_at | `(strategy_id, version)` unique; 발행 후 불변 |
| `screening_runs` | id, strategy_version_id, trading_date, as_of, universe_snapshot, status, started_at, finished_at, job_run_id | 동일 멱등 키 정책 필요 |
| `screening_results` | id, run_id, instrument_id, passed, score, rank, exclusion_reason | `(run_id, instrument_id)` unique |
| `rule_evaluations` | id, result_id, rule_key, observed_value, operator, threshold, passed, explanation | 결과 설명 스냅샷 |
| `signals` | id, instrument_id, strategy_version_id, screening_result_id, signal_type, strength, status, generated_at, valid_until, invalidation_reason | 주문이 아닌 관찰 이벤트 |

### 관심/포트폴리오

| 테이블 | 주요 컬럼 | 제약/설명 |
|---|---|---|
| `watchlists` | id, user_id, name, is_default | `(user_id, name)` unique |
| `watchlist_items` | id, watchlist_id, instrument_id, note, added_at | `(watchlist_id, instrument_id)` unique |
| `tags` | id, user_id, name, color | `(user_id, name)` unique |
| `watchlist_item_tags` | item_id, tag_id | 복합 PK |
| `portfolios` | id, user_id, name, base_currency | 단일 사용자라도 확장 가능한 경계 |
| `positions` | id, portfolio_id, instrument_id, quantity, average_cost, opened_at, closed_at, version | 활성 포지션 unique partial index 검토; optimistic lock |
| `portfolio_transactions` | id, position_id, transaction_type, traded_at, quantity, price, fee, tax, note | 사용자가 입력한 불변 원장; 수정은 정정 이벤트 선호 |

`positions`는 원장의 파생 상태로 보고 거래 추가와 같은 트랜잭션 안에서 일관성을 유지하거나 재계산 가능하게 한다. 실제 증권사 주문/체결을 의미하지 않는다.

### 알림/백테스트/작업

| 테이블 | 주요 컬럼 | 제약/설명 |
|---|---|---|
| `push_subscriptions` | id, user_id, endpoint_hash, endpoint_encrypted, p256dh_encrypted, auth_encrypted, expires_at, revoked_at | 구독 비밀 암호화; endpoint 중복 방지 |
| `notification_rules` | id, user_id, rule_type, conditions, quiet_hours, is_enabled | 검증된 schema version 포함 |
| `notification_events` | id, rule_id, signal_id, dedup_key, title, body, created_at | dedup_key unique |
| `notification_deliveries` | id, event_id, subscription_id, status, attempts, last_error_code, delivered_at, read_at | 전송 추적 |
| `backtest_runs` | id, strategy_version_id, requested_by, period, assumptions, universe_snapshot_ref, status, metrics, code_version | 입력/가정 불변 스냅샷 |
| `backtest_equity_points` | run_id, trading_date, equity, cash, exposure, drawdown | `(run_id, trading_date)` PK |
| `backtest_trades` | id, run_id, instrument_id, entry/exit dates/prices, quantity, fees, taxes, pnl, reason | 가상 체결임을 UI에서 명시 |
| `job_runs` | id, job_type, idempotency_key, status, priority, scheduled_at, locked_at, heartbeat_at, attempts, payload, result_summary | idempotency_key unique; `SKIP LOCKED` 후보 |
| `job_events` | id, job_run_id, level, event_type, message, metadata, occurred_at | 작업 진단 이력 |
| `outbox_events` | id, aggregate_type, aggregate_id, event_type, payload, occurred_at, published_at, attempts | 트랜잭션 outbox |

## 4. 인덱스 전략

- `daily_bars(instrument_id, trading_date DESC)`
- `daily_bars(trading_date, instrument_id)`는 횡단면 계산이 실제로 빈번할 때 추가
- `screening_runs(strategy_version_id, trading_date DESC)`
- `screening_results(run_id, passed, score DESC, instrument_id)`
- `signals(instrument_id, generated_at DESC)` 및 활성 상태 partial index
- `notification_deliveries(status, created_at)` partial index
- `job_runs(status, priority DESC, scheduled_at)` partial index
- 감사/이벤트 테이블의 시각 인덱스

인덱스는 예상만으로 과다 생성하지 않고 `EXPLAIN (ANALYZE, BUFFERS)`와 실제 쿼리 지표로 검증한다.

## 5. 무결성과 동시성

- `high >= greatest(open, close, low)`, 음수 거래량 금지 등 check constraint
- 전략 버전 발행 후 update 금지(애플리케이션 정책 + DB 권한/trigger 필요성 검토)
- 작업 선점은 `FOR UPDATE SKIP LOCKED`, heartbeat와 lease 만료로 복구
- 보유 수량 음수 허용 여부는 공매도 제외 정책에 따라 금지
- `positions.version`으로 낙관적 잠금
- 모든 외부 수집 행에 source와 ingested_at 기록
- migration은 forward-compatible 순서(컬럼 추가 → 코드 전환 → 제약/삭제)로 수행

## 6. 보존/파티셔닝/백업

- 가격 데이터: 백테스트 요구 기간 동안 보존; 삭제 전 라이선스 확인
- job 상세 로그: 90일 제안, 요약은 장기 보존
- 감사 로그: 1년 이상 제안(법/운영 요구 확인)
- raw provider payload: 기본 미보존 또는 짧은 격리 보존; 개인정보/라이선스 검토
- 일봉 규모는 초기 일반 테이블로 충분할 가능성이 높다. 행 수·쿼리 지연·vacuum 비용 임계치를 정한 뒤 연도별 range partition을 도입한다.
- 논리 백업 또는 관리 스냅샷을 일일 수행하고 암호화된 별도 위치에 보관한다. 백업 성공이 아니라 실제 복원 검증을 완료 조건으로 본다.

## 7. Migration 정책

- 모델 변경은 migration과 함께 리뷰
- 운영 DB에서 자동 `create_all` 금지
- 배포 전 백업과 migration dry-run
- destructive migration은 최소 2회 배포로 분리
- 데이터 backfill은 재시작 가능한 job으로 만들고 진행률/검증 쿼리를 정의
- rollback이 데이터 손실을 일으키는 경우 forward-fix 절차를 명시
