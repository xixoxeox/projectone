# Docker 및 AWS Lightsail 배포 설계

## 1. 목표 토폴로지

초기 비용과 단일 관리자 규모를 고려해 서울 리전의 한 Lightsail 인스턴스에 Docker 컨테이너를 운영한다.

```text
Internet
 → DNS
 → Lightsail static IP
 → host firewall (22 restricted, 80/443)
 → reverse-proxy container (TLS)
    ├→ frontend container (Next.js)
    └→ api container (FastAPI)
       └→ private Docker network
          ├→ PostgreSQL container + persistent volume
          ├→ worker container
          └→ scheduler container (single replica)

External encrypted backup → S3-compatible/AWS storage in separate failure domain
CI registry → versioned immutable images → deployment pull
```

단일 인스턴스는 호스트 장애 시 전체 중단되는 의도적 초기 절충이다. 가용성/RPO 요구가 높아지면 Lightsail Managed Database 또는 RDS, 다중 인스턴스/로드밸런서로 전환한다.

## 2. Docker 설계 원칙

향후 생성할 이미지/Compose는 다음 기준을 따른다.

- frontend/backend 각각 multi-stage build, 최소 runtime image, non-root user
- 명시적 버전/이미지 digest, `latest` 운영 배포 금지
- API/worker/scheduler는 같은 backend artifact로 코드 drift 방지
- 컨테이너 root filesystem read-only를 목표로 임시 경로만 tmpfs
- PostgreSQL만 영속 volume 사용; 사용자 업로드가 생기면 객체 저장소 사용
- healthcheck, stop grace period, resource limit, log rotation 설정
- DB는 host public port에 publish하지 않고 내부 network만 사용
- 개발/운영 Compose override와 환경을 분리
- 이미지에 `.env`, 인증서 private key, 소스 제어 credential을 포함하지 않음

## 3. 네트워크/TLS

- inbound 80은 443 redirect, 443만 서비스
- SSH는 고정 관리 IP 또는 Lightsail browser SSH/별도 접근 정책으로 제한; password 로그인 금지
- reverse proxy에서 TLS 1.2+, HSTS(검증 후), 보안 헤더, body/timeouts 설정
- `/api`는 동일 origin으로 proxy해 CORS/쿠키 위험을 단순화
- PostgreSQL과 worker는 외부 접근 불가
- DNS/인증서 자동 갱신 실패 알림을 구성

## 4. 배포 절차

1. PR에서 lint/type/test/build/security scan 수행
2. main 병합 후 commit SHA로 frontend/backend 이미지 빌드
3. registry에 immutable tag와 provenance/SBOM 저장
4. 운영 호스트가 제한된 deploy credential로 이미지 pull
5. DB 암호화 백업 및 migration 사전 점검
6. 호환 가능한 migration을 별도 one-off 단계로 실행
7. API/worker/frontend 순서와 호환성을 고려해 교체
8. readiness, smoke test, 작업 큐/데이터 신선도 확인
9. 배포 버전/시각/담당/결과 기록
10. 실패 시 이전 이미지 rollback 또는 migration forward-fix

운영 서버에서 `git pull && build`하는 방식은 재현성과 공급망 추적이 약해 권장하지 않는다.

## 5. CI/CD 설계

### PR 파이프라인

- 문서 링크/Markdown lint
- Backend format/lint, static type, unit/integration tests, migration consistency
- Frontend lint, typecheck, unit tests, production build
- OpenAPI breaking-change 검사
- E2E smoke (브라우저 기반)
- dependency/license/secret scan, image/파일시스템 취약점 scan

### Main/Release 파이프라인

- 동일 commit artifact 1회 빌드 및 서명/attestation
- registry push
- 운영 배포는 초기에는 GitHub Environment 수동 승인 권장
- 배포 후 HTTPS/API/로그인 없는 health smoke와 migration revision 확인
- 실패 시 자동 중단, 알림; 무조건 자동 DB rollback 금지

CI는 단기 OIDC 자격 증명을 우선하며 장기 AWS access key를 저장하지 않는다. 실제 Lightsail/registry 연동 방식은 선택한 registry와 배포 도구 확정 후 ADR로 기록한다.

## 6. 백업과 복구

- PostgreSQL 일일 논리 백업 + Lightsail snapshot을 서로 다른 목적에 사용
- 백업 전송/저장 암호화, 최소 7일 일일 + 4주 주간 보존 제안
- 운영 DB와 다른 failure domain/account 권한에 사본 유지
- 백업 파일 checksum, 크기, 성공 시각 모니터링
- 분기별 격리 환경 복구 훈련: 새 DB 복원 → migration revision → 행 수/무결성 → 애플리케이션 smoke
- 문서화된 RPO 24h/RTO 4h는 사용자 확인 후 조정

복구 우선순위: 호스트 확보 → 네트워크/비밀 → DB 복원 → migration 검증 → 앱 배포 → 데이터 수집 gap backfill → 신호 재계산.

## 7. 운영 관측/알림

- 호스트: CPU, memory, disk/inode, load, container restart
- PostgreSQL: 연결, locks, slow query, volume, backup age
- App: p95 latency, 5xx, auth failures, queue age, job failures
- Domain: 각 dataset `last_success_at`, stale 종목 수, 신호 계산 버전
- 인증서 만료와 외부 provider 인증 만료
- 로그는 rotation하고 가능하면 외부 집계로 전송해 호스트 장애 후에도 조사 가능하게 함

## 8. 용량/확장 기준

초기 인스턴스 크기는 부하 시험 후 확정한다. 다음이 지속되면 확장한다.

- 메모리 > 75%, CPU > 70%, disk > 70%
- API p95 또는 queue age SLO 위반
- 백테스트가 수집 작업을 지연
- DB I/O/connection이 병목

확장 순서: 쿼리/작업 최적화 → worker 자원/동시성 분리 → 관리형 PostgreSQL → Redis/전용 queue → frontend/CDN 또는 API 다중 인스턴스.

## 9. 운영 런북 목록

- 배포/롤백
- DB 백업/복원
- migration 실패
- disk full/인스턴스 교체
- provider rate limit/auth 장애
- 데이터 stale/오염 및 재수집
- refresh token/provider credential 유출과 순환
- push 알림 폭주 중단
- 백테스트 작업 고착/취소
