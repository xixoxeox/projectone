# Swing Trading Screener

KOSPI 스윙 트레이딩을 위한 **모바일 우선 종목 선정 및 의사결정 지원 플랫폼**의 설계 저장소다. 관리자 1명이 시장 상태, 스크리닝 결과, 관심/보유 종목, 매수 후보·위험/매도 신호, 웹 알림, 백테스트를 확인하는 것을 목표로 한다.

> 이 서비스는 투자 판단을 보조하며 주문을 생성·전송하지 않는다. 자동매매는 프로젝트 범위에 포함되지 않는다. 표시되는 신호는 수익을 보장하지 않는다.

## 현재 상태

**설계 단계(M0)**다. FastAPI/Next.js 애플리케이션, Dockerfile, Compose, 데이터베이스, API는 아직 구현하지 않았다. 저장소의 Markdown 파일은 다음 구현 단계의 계약과 의사결정 초안이다.

## 계획된 기술 스택

| 영역 | 기술 |
|---|---|
| Backend | FastAPI (Python) |
| Frontend | Next.js (TypeScript, 모바일 우선) |
| Database | PostgreSQL |
| ORM | SQLAlchemy |
| Authentication | JWT access + rotating refresh session |
| Container | Docker |
| Deployment | AWS Lightsail |

실제 버전은 구현 시작 시 공식 지원 상태와 호환성을 확인해 lockfile/ADR로 고정한다.

## 설계 문서

- [PROJECT_PLAN.md](PROJECT_PLAN.md): 목표, 범위, 요구사항, 위험, 질문
- [ARCHITECTURE.md](ARCHITECTURE.md): 시스템/Backend/Frontend/작업 구조
- [DATABASE_DESIGN.md](DATABASE_DESIGN.md): 관계, 테이블, 무결성, 보존
- [API_DESIGN.md](API_DESIGN.md): REST endpoint와 계약/오류 규약
- [DIRECTORY_STRUCTURE.md](DIRECTORY_STRUCTURE.md): 목표 구조, 의존성, 브랜치 전략
- [DEPLOYMENT.md](DEPLOYMENT.md): Docker, Lightsail, CI/CD, 백업/운영
- [SECURITY.md](SECURITY.md): 위협 모델, JWT, 비밀/환경변수, 방어
- [ROADMAP.md](ROADMAP.md): milestone, exit criteria, 테스트/완료 정의

## 핵심 아키텍처

초기에는 운영 복잡도와 비용을 낮추기 위해 Next.js, FastAPI API/worker, PostgreSQL을 Docker로 운영하는 **모듈러 모놀리스**를 채택한다. 데이터 수집·스크리닝·알림·백테스트는 요청 프로세스에서 분리된 비동기 작업으로 처리한다. 토스증권 연동은 공급자 어댑터 뒤에 격리하며 읽기 전용 기능만 허용한다.

## 제품 안전 원칙

1. 주문/자동매매 기능과 주문 권한을 설계·구현하지 않는다.
2. 모든 분석에 데이터 기준 시각과 신선도를 표시한다.
3. 신호의 규칙, 입력값, 전략/코드 버전을 추적한다.
4. 결측·지연·오염 데이터에서는 보수적으로 신호를 차단한다.
5. 백테스트는 비용과 편향을 통제하고 가정을 명시한다.
6. 금융 데이터 라이선스와 투자정보 관련 법률/면책을 출시 전에 검토한다.

## 구현 전 차단 질문

구현 전 최소한 다음을 확정해야 한다.

- 토스증권 Open API 공식 사양, 데이터 범위, 인증, 호출 한도, 사용/재배포 약관
- 일봉/장중 주기와 허용 지연, 초기 스크리닝 규칙
- 수동 포트폴리오와 읽기 전용 계좌 조회의 범위
- 수정주가/기업행위/상장폐지 데이터 기준
- AWS 리전·예산·도메인·RPO/RTO 및 웹 푸시 대상

전체 질문은 [PROJECT_PLAN.md](PROJECT_PLAN.md)의 “확정이 필요한 질문”을 따른다. 확인되지 않은 공급자 필드나 규칙은 추정 구현하지 않는다.

## 다음 단계

1. M0 질문에 대한 제품 결정을 기록한다.
2. 핵심 ADR(모듈 경계, 작업 큐, 인증 흐름, 배포 방식)을 승인한다.
3. M1에서만 scaffold와 개발/CI 기반을 생성한다.
4. 각 milestone exit criteria를 충족한 후 다음 단계로 진행한다.

구현 순서와 완료 조건은 [ROADMAP.md](ROADMAP.md)를 참조한다.
