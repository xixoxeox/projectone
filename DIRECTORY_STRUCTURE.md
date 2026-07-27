# 프로젝트 디렉터리 설계

> 아래는 **향후 생성할 목표 구조**다. 이번 단계에는 문서 외 디렉터리나 실행 파일을 생성하지 않는다.

```text
swing-trading-screener/
├── README.md
├── PROJECT_PLAN.md
├── ARCHITECTURE.md
├── DATABASE_DESIGN.md
├── API_DESIGN.md
├── DIRECTORY_STRUCTURE.md
├── DEPLOYMENT.md
├── SECURITY.md
├── ROADMAP.md
├── docs/
│   ├── adr/                       # 중요한 아키텍처 결정 기록
│   ├── runbooks/                  # 배포, 장애, 백업/복구 절차
│   └── diagrams/                  # 원본 다이어그램
├── backend/
│   ├── pyproject.toml
│   ├── migrations/
│   ├── src/screener/
│   │   ├── main.py                # FastAPI composition root
│   │   ├── config.py
│   │   ├── shared/                # 공통 타입/오류/DB, 최소화
│   │   └── modules/
│   │       ├── identity/
│   │       ├── market/
│   │       ├── screening/
│   │       ├── signals/
│   │       ├── watchlists/
│   │       ├── portfolio/
│   │       ├── notifications/
│   │       ├── backtesting/
│   │       └── operations/
│   └── tests/
│       ├── unit/
│       ├── integration/
│       ├── contract/
│       └── fixtures/
├── frontend/
│   ├── package.json
│   ├── src/
│   │   ├── app/                   # Next.js routes/layouts
│   │   ├── features/              # 도메인별 UI/queries/actions
│   │   ├── components/            # 재사용 UI primitives
│   │   ├── lib/                   # API client, auth, formatters
│   │   ├── styles/
│   │   └── types/                 # 생성 타입과 UI 타입 분리
│   └── tests/
│       ├── unit/
│       └── e2e/
├── infra/
│   ├── docker/                    # 향후 Dockerfile 관련 파일
│   ├── compose/                   # 향후 local/prod compose 정의
│   ├── proxy/                     # reverse proxy 설정
│   ├── scripts/                   # 배포/백업/복구 자동화
│   └── monitoring/
├── contracts/
│   └── openapi/                   # 검토/고정된 API 계약
├── .github/
│   ├── workflows/
│   ├── pull_request_template.md
│   └── CODEOWNERS
└── .env.example                   # 이름과 설명만, 비밀 없음
```

## 1. Backend 모듈 내부 표준

각 도메인 모듈은 필요에 따라 다음을 가진다.

```text
module/
├── domain/          # 엔티티 의미, 값 객체, 정책, repository protocol
├── application/     # commands, queries, DTO, use cases
├── infrastructure/  # SQLAlchemy models/repositories, provider adapters
└── presentation/    # FastAPI router와 API schemas
```

작은 모듈에 빈 계층을 강제하지 않는다. 모듈 간 호출은 공개 application interface를 통하며 다른 모듈의 ORM 모델을 import하지 않는다. 공통 폴더는 “모든 것”의 저장소가 되지 않게 제한한다.

## 2. Frontend feature 구조

```text
features/screening/
├── api/             # query/mutation과 schema adapter
├── components/      # feature 전용 컴포넌트
├── hooks/
├── model/           # UI state/derived selectors
└── tests/
```

라우트 파일은 조합과 데이터 경계에 집중하고 비즈니스 표시 로직은 feature로 이동한다. 범용 컴포넌트만 `components`에 두며 feature 간 깊은 import를 금지한다.

## 3. 의존성 방향

```text
presentation → application → domain
infrastructure → domain/application ports
composition root → all concrete adapters
```

도메인은 FastAPI, SQLAlchemy, 공급자 SDK, Next.js를 알지 않는다. 프론트는 DB 모델을 공유하지 않고 OpenAPI 계약만 공유한다.

## 4. 명명/파일 정책

- Python: `snake_case`, 타입/클래스 `PascalCase`; 모듈별 명확한 이름
- TypeScript: 파일 규칙은 구현 전 lint 합의, React component `PascalCase`
- API/DB: 외부 JSON과 DB column은 `snake_case`
- 테스트 파일은 대상과 가까운 의미 이름 사용
- 생성 산출물과 사람이 편집하는 계약을 구분
- repository에 빌드 결과, `.env`, DB dump, provider 응답, 인증 키를 커밋하지 않음

## 5. 브랜치 전략

소규모 팀에 맞는 **trunk-based development**를 권장한다.

- 보호 브랜치: `main` (항상 배포 가능)
- 짧은 작업 브랜치: `feat/...`, `fix/...`, `docs/...`, `chore/...`
- PR 필수: CI 통과, 최소 1회 리뷰(1인 운영이면 self-check checklist와 squash 정책)
- squash merge로 변경 단위 명확화; Conventional Commits 권장
- release tag: `vMAJOR.MINOR.PATCH`; 운영 배포 commit/tag 기록
- 장기 `develop` 브랜치는 병합 지연과 drift 때문에 두지 않음
- 미완성 기능은 feature flag 또는 UI 비노출로 main의 배포 가능성 유지

긴급 수정도 `hotfix/...` → PR → main → tag 흐름을 따른다. DB 변경은 backward compatibility와 rollback/forward-fix 계획을 PR에 포함한다.
