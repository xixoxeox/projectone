# 보안 설계

## 1. 위협 모델과 자산

핵심 자산은 관리자 자격 증명, JWT/refresh session, 토스증권 API credential, push subscription key, 포트폴리오 데이터, 전략/신호, 운영 DB/백업이다. 주요 위협은 credential stuffing, XSS/CSRF, 토큰 탈취·재사용, SSRF, SQL injection, 공급망 침해, 비밀 로그 노출, 무단 DB 접근, 알림 스팸, 데이터 변조다.

자동매매를 구현하지 않고 **주문 권한 credential을 보유하지 않는 것**이 가장 중요한 위험 축소 조치다.

## 2. 인증/세션

- 회원가입 endpoint 없음; 초기 관리자는 one-off 운영 절차로 생성
- 비밀번호는 Argon2id 권장(환경에 맞춘 cost 측정), 최소 길이와 유출 비밀번호 정책
- 로그인 실패 메시지 통일, IP/계정 기반 rate limit과 점진 지연
- JWT access: 5~15분 제안, `sub`, `iss`, `aud`, `exp`, `iat`, `jti`, role 포함; 강한 서명키와 알고리즘 allowlist
- Refresh: 7~30일 제안, 서버에는 hash만 저장, 매 사용 회전, family 재사용 감지 시 전체 family 폐기
- 쿠키 사용 시 `HttpOnly`, `Secure`, `SameSite=Lax/Strict`, 좁은 Path; state-changing 요청에 CSRF token/origin 검증
- 로그아웃/비밀번호 변경/침해 시 session revoke
- 단일 관리자라도 MFA(WebAuthn/TOTP)를 초기 안정화 후 우선 추가 권장

## 3. 인가

- 모든 보호 API에서 인증을 기본 거부(default deny)
- 역할은 초기 `admin` 하나여도 명시적으로 검사
- 리소스 소유권을 repository query 조건에 포함
- 운영/감사 endpoint는 별도 권한 경계
- 외부 provider adapter에는 시장 데이터 읽기 메서드만 제공
- 주문 관련 scope, endpoint, DTO, secret을 코드/환경 설계에 포함하지 않음

## 4. 웹/API 방어

- Pydantic/schema 기반 allowlist 검증, 문자열/배열/기간/요청 크기 제한
- SQLAlchemy parameter binding; 동적 정렬/필드는 whitelist
- UI 출력 escape, HTML 메모 금지 또는 엄격 sanitize, CSP nonce/hash
- 보안 헤더: CSP, HSTS, `X-Content-Type-Options`, `Referrer-Policy`, frame 차단
- 동일 origin 우선; CORS는 정확한 production origin만, wildcard+credentials 금지
- 외부 URL fetch가 필요하면 host allowlist, private/link-local IP 차단, redirect 재검증으로 SSRF 방지
- OpenAPI/docs와 상세 오류는 운영에서 인증/제한
- 웹 푸시 payload에 민감한 보유 수량/손익을 기본 포함하지 않고 앱 로그인 후 조회

## 5. 비밀 및 환경변수

### 비밀 분류

- `DATABASE_URL` 또는 개별 DB password
- `JWT_SIGNING_KEY`(또는 비대칭 private key), cursor/HMAC key
- 토스증권 client secret/access token(정확한 방식 미확정)
- VAPID private key
- 백업/registry/deploy credential

비밀은 `.env`에 커밋하지 않고 운영 호스트의 권한 제한 secret 파일 또는 검증된 secret store로 주입한다. Docker image layer, Compose 평문, CI 로그에 노출하지 않는다. 키에는 소유자, 용도, 생성/만료/순환일을 기록하며 침해 시 폐기 런북을 둔다.

### 제안 환경변수 카탈로그

| 범주 | 변수(제안) | 비밀 | 검증/기본 정책 |
|---|---|---:|---|
| App | `APP_ENV`, `APP_VERSION`, `LOG_LEVEL` | 아니오 | production에서 debug 금지 |
| Web | `PUBLIC_APP_URL`, `NEXT_PUBLIC_API_BASE_PATH` | 아니오 | same-origin path 권장; public 변수에 비밀 금지 |
| API | `API_BASE_PATH`, `ALLOWED_HOSTS`, `CORS_ORIGINS` | 아니오 | 명시 목록, wildcard 금지 |
| DB | `DATABASE_URL` | 예 | TLS/connection limit 검토, 로그 redaction |
| Auth | `JWT_ISSUER`, `JWT_AUDIENCE`, `JWT_ACCESS_TTL_SECONDS` | 아니오 | 범위 제한 |
| Auth | `JWT_SIGNING_KEY`, `REFRESH_TOKEN_PEPPER` | 예 | 충분한 entropy, 시작 시 필수 검증 |
| Provider | `TOSS_API_BASE_URL`, `TOSS_CLIENT_ID` | 일부 | 공식 host allowlist |
| Provider | `TOSS_CLIENT_SECRET`, `TOSS_ACCESS_TOKEN` | 예 | 실제 인증 방식 확인 전 확정 금지 |
| Push | `VAPID_PUBLIC_KEY` | 아니오 | 공개 가능 |
| Push | `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT` | 예/일부 | private key 보호 |
| Jobs | `WORKER_CONCURRENCY`, `JOB_LEASE_SECONDS`, `SCHEDULER_ENABLED` | 아니오 | scheduler 단일 인스턴스 |
| Market | `MARKET_TIMEZONE`, `DATA_STALE_AFTER_SECONDS` | 아니오 | timezone=`Asia/Seoul` |
| Ops | `SENTRY_DSN` 등 | 예 취급 | PII/토큰 scrub |
| Backup | `BACKUP_DESTINATION`, provider credentials | 예 | 앱 runtime과 권한 분리 |

`.env.example`에는 변수명, 설명, 안전한 placeholder만 두며 실제 값과 운영 hostname/계정 정보를 넣지 않는다. 앱은 시작 시 타입, 범위, 상호 의존성을 검증하고 필수 비밀이 없으면 fail fast 한다.

## 6. 데이터 보호/개인정보

- HTTPS 전송 암호화, 백업/볼륨 암호화 기능 활성화
- push endpoint/key는 암호화 저장; 검색용 hash 별도
- 비밀번호/refresh token은 단방향 hash
- 로그에 Authorization, Cookie, password, token, DB URL, portfolio 상세를 redaction
- 데이터 최소 수집 및 보존 기간 종료 자동 삭제
- 관리자 데이터 export/delete 요구가 생길 경우 감사 가능한 절차 마련
- 법률 검토를 통해 개인정보 처리방침, 이용약관, 투자 면책, 데이터 공급자 표시 확정

## 7. 공급망/운영 보안

- lockfile과 dependency update bot, CVE/license scan
- base image digest pinning, 최소 이미지, non-root, SBOM/서명
- GitHub branch protection, mandatory CI, secret scanning
- CI는 OIDC/단기 credential, production environment 승인
- SSH key only, fail2ban 또는 동등 제어, OS 자동 보안 업데이트 정책
- DB public exposure 금지, 최소 DB role(app/migration/backup 역할 분리 권장)
- 정기 복구 훈련과 접근 권한 검토

## 8. 감사 이벤트

로그인 성공/실패, refresh 재사용, 로그아웃-all, 전략 발행/활성화, 스크리닝/백테스트 요청, 포트폴리오 변경, 알림 규칙 변경, 데이터 재수집, 비밀 순환, 운영 작업을 감사한다. 감사 로그는 append-only이며 before/after에 비밀이나 불필요한 개인 데이터를 남기지 않는다.

## 9. 보안 검증 체크리스트

- 인증/인가/소유권 negative test
- CSRF, XSS, CSP, CORS 검증
- JWT alg/iss/aud/exp/reuse test 및 시간 오차 처리
- rate limit과 lockout DoS 균형
- SSRF/DNS rebinding 방어(외부 URL 기능이 있을 때)
- dependency/container/secret scan
- 백업 접근 및 복원 검증
- provider credential이 읽기 전용인지 확인
- 주문 기능/권한이 어떤 경로에도 없는지 release gate로 확인
