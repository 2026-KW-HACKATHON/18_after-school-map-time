# 인프라 설계

> 담당: 강성훈. 스택: Django + Gunicorn + PostgreSQL + Nginx, Docker Compose, AWS EC2 1대, GitHub Actions 자동 배포.
> 해커톤 규모이므로 RDS·로드밸런서·쿠버네티스는 쓰지 않는다. **단순하고, 팀원 전원이 설명할 수 있는 구성**이 목표.

---

## 1. 구조

```
사용자 (모바일 브라우저)
   │ HTTPS 443 (HTTP 80은 443으로 리다이렉트)
   ▼
[nginx]  ── SSL 종료, /static/ · /media/ 직접 서빙, 나머지는 web으로 프록시
   │ http://web:8000
   ▼
[web]    ── Django + Gunicorn
   │
   ▼
[db]     ── PostgreSQL 16, named volume에 데이터 유지 (외부 포트 노출 없음)
```

| 환경 | 파일 | web 실행 | 비고 |
|---|---|---|---|
| 개발 | `docker-compose.yml` | `runserver` + 코드 볼륨 마운트 | `localhost:8000`, db 5432 노출 허용 |
| 배포 | `docker-compose.prod.yml` | `gunicorn` (Docker Hub 이미지) | nginx 포함, `restart: unless-stopped` |

### 볼륨

- `postgres_data` — DB 데이터
- `static_volume` — `collectstatic` 결과. web이 쓰고 nginx가 읽음
- `media_volume` — 제보 사진. web이 쓰고 nginx가 읽음. **백업 대상**
- SSL 인증서 — 호스트의 `/etc/letsencrypt`를 nginx에 읽기 전용 마운트 (아래 4절)

---

## 2. 환경 변수 (`.env.example`에 들어갈 항목)

| 변수 | 설명 | 개발 예시 |
|---|---|---|
| `SECRET_KEY` | Django 시크릿 키 (비어 있으면 에러로 즉시 알림) | 생성 명령 주석 참고 |
| `DEBUG` | 디버그 모드 | `True` / 배포 `False` |
| `ALLOWED_HOSTS` | 콤마 구분 | `localhost,127.0.0.1` |
| `CSRF_TRUSTED_ORIGINS` | 콤마 구분, https 포함 | 배포: `https://<도메인>` |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | Postgres 컨테이너 초기값 | 개발은 단순값, **배포는 강한 비밀번호** |
| `DATABASE_URL` | 비우면 SQLite 폴백 | `postgres://teokeopne:teokeopne@db:5432/teokeopne` |
| `KAKAO_JAVASCRIPT_KEY` | 카카오맵 JS 키 (브라우저 노출됨 → 플랫폼 Web 도메인 등록 필수) | |
| `KAKAO_REST_API_KEY` | 카카오 REST 키 (서버 전용: 주소→좌표 등) | |
| `AI_VISION_API_KEY` | AI 사진 판별 API 키 (서비스 미정) | |
| `DOMAIN` | 배포 도메인 (nginx 설정·문서용) | 배포에서만 |

- 배포용 `.env`는 **EC2 서버에만** 둔다. GitHub Secrets에는 배포 접속 정보만 둔다.
- 새 변수를 추가하면 `.env.example`과 README 환경 변수 표를 같이 갱신한다.

---

## 3. Django 설정 요점

- 원본(Dopamine-Ledger) 방식 유지: `python-dotenv` + `dj-database-url`, `DEBUG` 기본 False
- 추가:
  - `SECRET_KEY`가 비어 있으면 `ImproperlyConfigured`로 실패
  - `CSRF_TRUSTED_ORIGINS` 환경변수 파싱
  - `DEBUG=False`일 때: `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`
  - 업로드: `DATA_UPLOAD_MAX_MEMORY_SIZE`, `FILE_UPLOAD_MAX_MEMORY_SIZE`를 Nginx 제한(10MB)과 맞춤
  - 로깅: 콘솔 출력 (`docker compose logs`로 확인)
- `/health/`: DB에 `SELECT 1` 후 200 JSON. 실패 시 503. (인프라용 작은 `core` 앱 또는 `config/urls.py`에 둠)

---

## 4. Nginx · HTTPS

### Nginx 요구사항

- `client_max_body_size 10M;` — 기본 1MB면 폰 사진이 413 에러
- `proxy_read_timeout 60s;` — AI 판별 대기
- 헤더: `Host`, `X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Proto`
- `/static/` → `static_volume`, `/media/` → `media_volume` (정적 파일 캐시 헤더)
- 80 → 443 리다이렉트, 단 `/.well-known/acme-challenge/`는 80에서 응답 (인증서 발급·갱신용)
- gzip 켜기 (모바일 로딩)

### HTTPS 방식 (권장안 — 사용자 확인)

- 호스트(EC2)에 certbot 설치 → **webroot 방식**으로 발급
  - nginx가 `/.well-known/acme-challenge/`를 호스트 디렉토리(예: `/var/www/certbot`)에서 서빙
  - 발급된 `/etc/letsencrypt`를 nginx 컨테이너에 읽기 전용 마운트
  - 갱신: certbot 자동 갱신 + `--deploy-hook`으로 `docker compose exec nginx nginx -s reload`
- 첫 발급 시 인증서가 아직 없어 443 블록이 에러나는 문제 → **HTTP 전용 설정으로 먼저 띄워 발급 → HTTPS 설정으로 교체** 순서를 배포 문서에 명시
- 대안: 이전 프로젝트에서 쓴 DuckDNS + acme.sh 조합도 가능. 도메인이 정해지면 결정.

### 왜 HTTPS가 필수인가

제보 기능의 "현재 위치 자동 입력"은 브라우저 Geolocation API를 쓰는데, 이 API는 HTTPS(또는 localhost)에서만 동작한다.
또한 대회 규정상 localhost·IP 접속은 불이익 대상이다.

---

## 5. AWS EC2

- 리전: 서울(ap-northeast-2), OS: Ubuntu LTS
- 인스턴스: **t3.small (RAM 2GB)** 권장. 1GB급이면 swap 2GB 필수.
- EBS: 20GB 이상 (Docker 이미지가 쌓여 디스크가 차기 쉬움 → 배포마다 `docker image prune -f`)
- **탄력적 IP** 할당 (재시작 시 IP 변경 방지)
- 보안 그룹: 22 → 팀장 IP만 / 80, 443 → 전체 / **5432는 열지 않음**
- 서버 디렉토리: 레포를 `~/teokeopne`에 clone, 그 안에 배포용 `.env` 생성
- 백업: `scripts/backup_db.sh`를 cron으로 매일 실행, 최근 N일치만 보관. 전시 기간 전 media 폴더도 백업.

> AWS 리소스 생성·도메인 구매·Secrets 등록은 사람이 직접 한다.
> Claude Code는 이 과정을 따라 하기만 하면 되는 **런북(`docs/deploy.md`)** 을 작성한다.

---

## 6. CI/CD

```
develop push (또는 Actions에서 수동 실행)
  → Docker 이미지 빌드
  → Docker Hub push (`latest` + 커밋 SHA 태그)
  → EC2 SSH 접속
  → cd ~/teokeopne && git pull origin develop
  → docker compose -f docker-compose.prod.yml pull
  → docker compose -f docker-compose.prod.yml up -d
  → migrate → collectstatic
  → docker image prune -f
  → /health/ 확인
```

- EC2 준비 전까지는 `push` 트리거를 주석 처리하고 `workflow_dispatch`(수동 실행)만 켜 둔다.
- 필요한 GitHub Secrets: `DOCKER_USERNAME`, `DOCKER_PASSWORD`(Docker Hub 액세스 토큰 권장), `EC2_HOST`, `EC2_KEY`

---

## 7. 주의사항 체크리스트

- [ ] `.env`, `*.pem`, API 키가 커밋 이력에 없다 (public 전환 전 `git log -p`로 재확인)
- [ ] 카카오 개발자센터 플랫폼(Web)에 허용 도메인만 등록 (개발 `http://localhost:8000`, 배포 `https://<도메인>`)
- [ ] 폰 사진 업로드(3~8MB)가 413 없이 된다
- [ ] 배포 구성에서 `DEBUG=False`, db 포트 미노출
- [ ] 인증서 자동 갱신 동작 확인 (`certbot renew --dry-run`)
- [ ] 전시(10/11~13) 전에 DB·media 백업, 재부팅 후 자동 복구 확인
