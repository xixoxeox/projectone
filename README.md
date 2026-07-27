# Swing Trading Screener

## Toss read-only market data

Sprint 3 integrates the official Toss Securities Open API 1.2.4 for OAuth, daily
candles, prices, stock master metadata, and warnings. Configuration and contract
details are documented in [`docs/TOSS_API_INTEGRATION.md`](docs/TOSS_API_INTEGRATION.md).
Development starts with an `unconfigured` provider when credentials are absent;
production fails settings validation. Account and order functionality is intentionally
excluded.

KOSPI 스윙 트레이딩을 위한 모바일 우선 의사결정 지원 플랫폼입니다. **주문 및 자동매매 기능은 제공하지 않습니다.** Sprint 2는 공급자 중립 시장 데이터 계층과 읽기 전용 Toss 어댑터 기반을 추가합니다. 공식 Toss 계약이 저장소에 없어 라이브 경로/필드 매핑은 의도적으로 비활성화되어 있습니다.

## 구성

- `frontend`: Next.js App Router / TypeScript 로그인 및 보호된 대시보드
- `backend`: 계층형 FastAPI API, SQLAlchemy 2.x, Alembic
- PostgreSQL: 최소 `users`, `refresh_sessions` 테이블
- JWT access token과 회전형 HttpOnly refresh cookie, Argon2id 비밀번호 해시
- Docker Compose 개발 환경 및 GitHub Actions CI

상세 결정은 [ARCHITECTURE.md](ARCHITECTURE.md), [API_DESIGN.md](API_DESIGN.md), [DATABASE_DESIGN.md](DATABASE_DESIGN.md), [SECURITY.md](SECURITY.md)를 참고하세요.
시장 데이터 경계, 환경 변수, 확인되지 않은 공식 API 항목과 mock 테스트 방법은 [PROVIDER_ARCHITECTURE.md](PROVIDER_ARCHITECTURE.md)를 참고하세요. Toss 자격 증명과 토큰은 로그/DB/API 응답에 기록하지 않으며 통합은 주문 기능 없는 읽기 전용입니다.

## 로컬 실행

필수 도구는 Docker Compose입니다.

```bash
cp .env.example .env
# .env의 DB 비밀번호와 두 인증 비밀을 안전한 임의 값으로 교체
docker compose up --build -d db
docker compose run --rm backend alembic -c /app/alembic.ini upgrade head
docker compose up --build
```

API 문서는 `http://localhost:8000/docs`, liveness는 `http://localhost:8000/api/v1/health/live`, 웹은 `http://localhost:3000`에서 확인합니다.

### 관리자 생성

회원가입 API는 없습니다. Backend 개발 환경에서 migration 후 일회성 명령을 실행합니다.

```bash
cd backend
ADMIN_USERNAME=admin ADMIN_PASSWORD='replace-with-a-strong-password' python scripts/create_admin.py
```

### 직접 개발

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
alembic upgrade head
uvicorn screener.main:app --reload
```

```bash
cd frontend
npm install
npm run dev
```

## 검증

```bash
cd backend && ruff check . && ruff format --check . && mypy src && pytest
cd frontend && npm run lint && npm run typecheck && npm test && npm run build
```

## 인증 흐름

로그인은 짧은 수명의 access JWT를 응답하고 refresh token은 제한된 경로의 HttpOnly cookie에 저장합니다. Refresh 시 서버 세션을 폐기하고 새 토큰으로 회전합니다. 프론트는 access token을 메모리에만 보관하며 보호 화면 진입 시 refresh 후 `/auth/me`를 확인합니다. 운영 환경에서는 강한 독립 비밀, HTTPS, `REFRESH_COOKIE_SECURE=true`, 정확한 CORS origin이 필수입니다.
