# API 설계

## 1. 규약

- Base path: `/api/v1`
- 형식: JSON, UTF-8, `snake_case`
- 시각: UTC ISO 8601 (`2026-07-27T09:00:00Z`), 거래일은 `YYYY-MM-DD`
- 인증: 짧은 수명의 JWT access token + 회전형 refresh session
- 버전: breaking change는 path major version; 추가 필드는 호환 변경
- 문서: FastAPI OpenAPI를 생성하되 운영 공개 범위 제한
- 요청 추적: 요청/응답 `X-Request-ID`
- 금액/정밀 숫자: JSON 문자열 전송을 기본 검토하여 부동소수점 손실 방지

모든 시장/신호 응답은 가능한 경우 다음 메타데이터를 포함한다.

```json
{
  "data": {},
  "meta": {
    "as_of": "2026-07-27T06:30:00Z",
    "timezone": "Asia/Seoul",
    "is_stale": false,
    "source": "provider-key",
    "request_id": "uuid"
  }
}
```

예시는 계약 설명이며 구현 코드가 아니다.

## 2. 인증 API

| Method | Path | 설명 | 응답 |
|---|---|---|---|
| POST | `/auth/login` | 관리자 ID/비밀번호 검증 | access token과 refresh cookie/session |
| POST | `/auth/refresh` | refresh 회전 및 access 재발급 | 새 access/refresh |
| POST | `/auth/logout` | 현재 refresh session 폐기 | `204` |
| POST | `/auth/logout-all` | 모든 session 폐기 | `204` |
| GET | `/auth/me` | 현재 관리자/세션 정보 | 사용자 요약 |

로그인 오류는 사용자 존재 여부를 노출하지 않는다. Refresh는 `HttpOnly`, `Secure`, 적절한 `SameSite` cookie를 우선하며 access token 전달 방식은 Next.js 배포 토폴로지와 CSRF 모델을 ADR로 확정한다.

## 3. 시장/종목 API

| Method | Path | 설명 |
|---|---|---|
| GET | `/market/summary` | 지수, 시장 폭, 국면, 데이터 신선도 |
| GET | `/market/calendar` | 거래일/세션 조회 |
| GET | `/instruments` | KOSPI 종목 검색·필터·cursor 페이지 |
| GET | `/instruments/{instrument_id}` | 종목 메타데이터와 상태 |
| GET | `/instruments/{instrument_id}/bars` | 제한된 기간의 일봉/수정주가 |
| GET | `/instruments/{instrument_id}/indicators` | 계산된 기술 지표와 버전 |
| GET | `/instruments/{instrument_id}/signals` | 신호 이력/근거 |

검색 입력 길이, 날짜 범위, page size(기본 20, 최대 100)를 제한한다. 종목 ID는 불투명 식별자를 사용한다.

## 4. 스크리닝 API

| Method | Path | 설명 |
|---|---|---|
| GET | `/strategies` | 활성 전략/발행 버전 목록 |
| GET | `/strategies/{strategy_id}/versions/{version}` | 규칙과 설명 조회 |
| POST | `/screening-runs` | 전략/거래일로 비동기 실행 요청 (`202`) |
| GET | `/screening-runs` | 실행 이력 |
| GET | `/screening-runs/{run_id}` | 상태/요약/신선도 |
| GET | `/screening-runs/{run_id}/results` | 통과 여부, 점수, 순위 목록 |
| GET | `/screening-runs/{run_id}/results/{instrument_id}` | 규칙별 평가 근거 |

`POST`는 `Idempotency-Key`를 받고 동일 사용자·입력에 중복 작업을 만들지 않는다. 완료되지 않은 결과를 부분 성공처럼 노출하지 않는다.

## 5. 관심/보유 API

| Method | Path | 설명 |
|---|---|---|
| GET/POST | `/watchlists` | 목록 조회/생성 |
| PATCH/DELETE | `/watchlists/{id}` | 이름 변경/삭제 |
| GET/POST | `/watchlists/{id}/items` | 항목 조회/추가 |
| PATCH/DELETE | `/watchlists/{id}/items/{item_id}` | 메모/태그 변경, 삭제 |
| GET/POST | `/portfolios` | 포트폴리오 조회/생성 |
| GET | `/portfolios/{id}/positions` | 보유 현황과 평가 기준 시각 |
| POST | `/portfolios/{id}/transactions` | 수동 거래 기록 추가 |
| POST | `/portfolios/{id}/transactions/{id}/corrections` | 정정 기록 추가 |
| GET | `/portfolios/{id}/performance` | 기간 성과/비교지수 |

금융 원장을 직접 덮어쓰기보다 정정 이벤트를 남긴다. 모든 쓰기는 소유권을 확인하며 단일 관리자라는 가정에 의존한 권한 생략을 하지 않는다.

## 6. 알림/백테스트/운영 API

| Method | Path | 설명 |
|---|---|---|
| GET/POST | `/notification-rules` | 규칙 조회/생성 |
| PATCH/DELETE | `/notification-rules/{id}` | 규칙 변경/삭제 |
| POST | `/push-subscriptions` | 브라우저 push 구독 등록 |
| DELETE | `/push-subscriptions/{id}` | 구독 해제 |
| GET | `/notifications` | 알림 피드 |
| POST | `/notifications/{id}/read` | 읽음 처리 |
| POST | `/backtest-runs` | 비동기 백테스트 요청 (`202`) |
| GET | `/backtest-runs` | 실행 목록 |
| GET | `/backtest-runs/{id}` | 상태, 가정, 결과 지표 |
| GET | `/backtest-runs/{id}/trades` | 가상 거래 목록 |
| GET | `/backtest-runs/{id}/equity` | 자산 곡선 |
| POST | `/backtest-runs/{id}/cancel` | 취소 요청 |
| GET | `/jobs/{id}` | 작업 상태/안전한 오류 요약 |
| GET | `/operations/data-freshness` | 데이터셋별 마지막 성공/신선도 |
| GET | `/health/live`, `/health/ready` | 오케스트레이션 점검 |

## 7. 오류 계약

RFC 9457 Problem Details 형태를 채택한다.

```json
{
  "type": "https://example.invalid/problems/stale-market-data",
  "title": "Market data is stale",
  "status": 409,
  "detail": "Screening was not started because required data is stale.",
  "code": "STALE_MARKET_DATA",
  "request_id": "uuid",
  "errors": []
}
```

| Status | 사용 |
|---:|---|
| 400 | 구문/일반 요청 오류 |
| 401 | 인증 없음/만료 |
| 403 | 권한/소유권 실패 |
| 404 | 리소스 없음(권한 은폐 포함) |
| 409 | 상태 충돌, stale data, 중복 |
| 422 | 필드 검증 오류 |
| 429 | 호출 제한 |
| 503 | 필수 의존성/데이터 준비 안 됨 |

공급자 원문 오류, stack trace, SQL 정보는 응답하지 않는다.

## 8. Pagination, 정렬, 필터

```text
GET /api/v1/screening-runs/{id}/results?passed=true&sort=-score&limit=20&cursor=opaque
```

응답은 `items`, `next_cursor`, `has_more`를 포함한다. 허용된 필터/정렬 필드만 whitelist하고 cursor는 위변조 방지 서명 또는 서버가 검증 가능한 인코딩을 사용한다.

## 9. 동시성, 제한, 캐시

- 변경 API는 필요한 곳에 `version` 또는 `If-Match`를 사용해 lost update 방지
- 로그인, refresh, 백테스트, 스크리닝 실행은 별도 rate limit
- GET 캐시는 사용자별 데이터가 섞이지 않도록 `private`/`no-store` 정책 구분
- 신호/포트폴리오 응답은 오래된 캐시보다 정확성을 우선
- 비동기 실행의 상태는 `queued/running/succeeded/failed/cancel_requested/cancelled`

## 10. 계약 테스트 원칙

- OpenAPI schema 변경 diff를 CI에서 검사
- 정상/인증/권한/검증/충돌/공급자 장애 예시를 테스트
- 프론트 타입은 고정된 OpenAPI artifact에서 생성하는 방안을 권장
- 시간대, Decimal 직렬화, cursor, idempotency, stale-data 오류를 핵심 계약으로 취급
