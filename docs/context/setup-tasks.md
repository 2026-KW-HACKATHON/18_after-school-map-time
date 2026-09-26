# 기본 세팅 작업 목록 (Claude Code 수행용)

> 팀장이 Claude Code로 레포 틀을 이미 일부 만들어 둔 상태다.
> **처음부터 새로 만들지 말고, 현재 레포를 점검해서 빠진 것만 채운다.**
> 각 작업은 완료 기준을 실제로 확인한 뒤 커밋한다. push·머지는 사용자 확인 후.

작업 브랜치: `chore/infra-setup` (없으면 `develop`에서 생성)

---

## T0. 현재 상태 점검 (코드 수정 없음)

1. 레포 전체 구조, 기존 설정 파일을 읽는다.
2. 필요하면 참고 레포를 임시 폴더에 클론해 비교한다 (`conventions.md` 상단 명령).
3. 아래 T1~T7 체크리스트 기준으로 **있음 / 수정 필요 / 없음** 표를 만들어 사용자에게 보고한다.
4. `CLAUDE.md`의 "미정 사항" 중 이번 작업에 필요한 것을 한 번에 질문한다.
   (최소: 프론트엔드 방식, Docker Hub 이미지 이름, 디스코드 문의 링크)

**완료 기준:** 사용자가 점검 결과와 답변을 확인함

---

## T1. 레포 규칙 파일

- [ ] `.github/ISSUE_TEMPLATE/` — `feature.md`, `bug.md`, `design.md`, `docs.md`, `chore.md`, `config.yml`
- [ ] `.github/pull_request_template.md`
- [ ] `CONTRIBUTING.md` — 원본 구성 + 이번 레포 추가 규칙 (`conventions.md` 참고)
- [ ] `README.md` 뼈대 — 원본 섹션 순서 + "📚 오픈소스 / 출처" 섹션. 기능 표는 Must(F1~F6)만 "예정"으로 표기
- [ ] `.gitignore`, `.dockerignore` — 원본 기준 + `staticfiles/`, `media/`, `backups/`
- [ ] `.gitattributes` — `* text=auto`, `*.sh text eol=lf`

커밋 예: `docs: 이슈·PR 템플릿 추가`, `docs: CONTRIBUTING 작성`, `chore: gitignore·gitattributes 설정`

---

## T2. Django 기본 설정

- [ ] `config/` 프로젝트 (없으면 `django-admin startproject config .`)
- [ ] `settings.py` — `infra.md` 3절 요구사항 반영 (원본의 환경변수 방식 + HTTPS·업로드·SECRET_KEY 검증)
- [ ] `/health/` 엔드포인트 (DB 확인 포함) + 테스트 1개
- [ ] `requirements.txt` — 섹션 주석, 버전 고정, 용도 주석
  - 코어: Django, python-dotenv, dj-database-url, psycopg2-binary(또는 psycopg), gunicorn, pillow
  - 프론트 방식이 "템플릿 + DRF API"면 djangorestframework
  - 버전은 설치 가능한 최신 안정 버전으로 확인해서 고정
- [ ] 도메인 앱(장소·제보 등)은 **만들지 않는다** — 팀 ERD 확정 후 별도 이슈

**완료 기준:** `python manage.py check --deploy`를 `DEBUG=False` 설정으로 돌렸을 때 치명적 경고가 없음 (HSTS 등 의도적으로 미룬 항목은 주석으로 이유 표시)

---

## T3. Docker 개발 환경

- [ ] `Dockerfile` — 원본 구조 + gunicorn 옵션 (`--workers 3 --timeout 60` 정도)
- [ ] `docker-compose.yml` — web(runserver, 볼륨 마운트, 8000) + db(postgres:16, healthcheck, 5432)
- [ ] `.env.example` — `infra.md` 2절 항목, 섹션 주석

**완료 기준 (실제 실행해서 확인):**
```bash
cp .env.example .env   # SECRET_KEY 채우기
docker compose up --build -d
docker compose exec web python manage.py migrate
curl -i http://localhost:8000/health/   # 200
docker compose exec web python manage.py test
docker compose down
```

---

## T4. 배포 구성 (nginx 포함)

- [ ] `docker-compose.prod.yml` — nginx / web(gunicorn, Docker Hub 이미지) / db, 볼륨 3개, `restart: unless-stopped`, db 포트 미노출, healthcheck
- [ ] `nginx/` — HTTP 전용 설정(첫 인증서 발급용)과 HTTPS 설정 두 가지. 요구사항은 `infra.md` 4절
- [ ] 로컬 검증용: 도메인·인증서 없이 HTTP 전용 설정으로 띄울 수 있게 한다 (환경변수나 별도 override 파일 등 방법은 단순한 쪽으로)

**완료 기준:**
```bash
docker compose -f docker-compose.prod.yml up --build -d   # DEBUG=False
curl -i http://localhost/health/                           # 200 (nginx 경유)
curl -I http://localhost/static/admin/css/base.css          # 200 (nginx가 직접 서빙)
# 8MB 정도의 파일 업로드 테스트 → 413이 나지 않음
docker compose -f docker-compose.prod.yml down
```

---

## T5. CI/CD 워크플로우

- [ ] `.github/workflows/deploy.yml` — 원본 흐름 + `infra.md` 6절 개선점
- [ ] 상단에 주석 블록 (무엇을 하는지, 필요한 Secrets)
- [ ] **EC2 준비 전이므로 `push` 트리거는 주석 처리, `workflow_dispatch`만 활성화**

**완료 기준:** YAML 문법 검증 (가능하면 `actionlint`), 사용자에게 Secrets 등록 목록 안내

---

## T6. 배포 런북 `docs/deploy.md`

사람이 위에서부터 따라 하면 배포가 끝나는 문서. 명령어는 복사해서 바로 쓸 수 있게.

1. EC2 생성 (사양, 보안 그룹, 탄력적 IP, 키페어)
2. 서버 초기 설정 (swap, Docker 설치, 레포 clone, 배포용 `.env` 작성)
3. 도메인 연결 (A 레코드)
4. 첫 인증서 발급 (HTTP 설정으로 기동 → certbot webroot 발급 → HTTPS 설정 전환 → 갱신 hook)
5. GitHub Secrets 등록, `deploy.yml` 수동 실행, `push` 트리거 활성화
6. 백업 cron 등록, 확인 체크리스트 (`infra.md` 7절)
7. 문제 해결 (로그 보기, 디스크 정리, 롤백: 이전 SHA 태그로 되돌리기)

---

## T7. 운영 스크립트

- [ ] `scripts/backup_db.sh` — `pg_dump` → `backups/날짜.sql.gz`, 오래된 파일 정리, 한국어 주석
- [ ] 실행 권한 + LF 줄바꿈 확인

---

## 마무리

- README의 "시작하기"와 "프로젝트 구조"를 실제 결과에 맞게 갱신
- 작업 요약(바뀐 파일, 사람이 해야 할 일: AWS·도메인·Secrets)을 사용자에게 보고
- `develop`으로 PR 생성은 사용자 확인 후
