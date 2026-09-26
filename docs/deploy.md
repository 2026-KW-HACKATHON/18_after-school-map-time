# 🚀 배포 런북 (AWS EC2 + Docker Compose + HTTPS)

위에서부터 순서대로 따라 하면 **`https://<도메인>`으로 턱없네가 뜨고, `develop`에 머지하면 자동 배포**되는 상태가 됩니다.
명령어는 복사해서 그대로 쓰면 되고, `<...>` 부분만 자기 값으로 바꿉니다.

```
사용자 ─HTTPS─▶ [nginx] ─▶ [web: Django + gunicorn] ─▶ [db: PostgreSQL]
                  └ /static/ /media/ 직접 서빙
```

| 단계 | 내용 | 어디서 |
| --- | --- | --- |
| 1 | EC2 생성 · 보안 그룹 · 탄력적 IP | AWS 콘솔 |
| 2 | 서버 초기 설정 (swap, Docker, 레포 clone, `.env`) | EC2 (SSH) |
| 3 | 도메인 연결 | DuckDNS / 도메인 업체 |
| 4 | 첫 기동 + 인증서 발급 + HTTPS 전환 | EC2 |
| 5 | GitHub Secrets 등록 · 자동 배포 켜기 | GitHub |
| 6 | 백업 cron · 최종 점검 | EC2 |
| 7 | 문제 해결 | — |

---

## 1. EC2 생성 (AWS 콘솔)

EC2 → **인스턴스 시작**

| 항목 | 값 |
| --- | --- |
| 리전 | 아시아 태평양(서울) `ap-northeast-2` |
| 이름 | `teokeopne` |
| AMI | **Ubuntu Server 24.04 LTS** |
| 인스턴스 유형 | **t3.small** (RAM 2GB). t3.micro(1GB, 프리티어)면 2단계 swap 필수 |
| 키 페어 | 새로 생성 → RSA, `.pem` → 다운로드한 파일은 **레포 밖**에 보관 (절대 커밋 금지) |
| 스토리지 | **30GB gp3** (Docker 이미지가 쌓이므로 여유 있게) |

**보안 그룹** (인바운드 규칙)

| 유형 | 포트 | 소스 | 이유 |
| --- | --- | --- | --- |
| SSH | 22 | **내 IP** | 서버 접속 |
| HTTP | 80 | 0.0.0.0/0 | 인증서 발급·https 리다이렉트 |
| HTTPS | 443 | 0.0.0.0/0 | 서비스 |

> ❌ 5432(PostgreSQL)는 **열지 않습니다.** DB는 서버 안의 web 컨테이너만 접근합니다.
>
> ⚠️ SSH를 "내 IP"로 막으면 GitHub Actions도 접속할 수 없습니다. 5단계에서 자동 배포를 쓰려면 22번 소스를 `0.0.0.0/0`으로 열어야 합니다 (키 파일 없이는 접속 불가하므로 해커톤 규모에선 허용 범위).

**탄력적 IP**: EC2 → 탄력적 IP → 할당 → 방금 만든 인스턴스에 **연결**. (재시작해도 IP가 안 바뀜) 이 IP를 이하 `<EIP>`라고 부릅니다.

---

## 2. 서버 초기 설정 (SSH)

내 PC에서 접속 (Git Bash):

```bash
chmod 400 ~/keys/teokeopne.pem
ssh -i ~/keys/teokeopne.pem ubuntu@<EIP>
```

### 2-1. 시간대 · swap 2GB

```bash
sudo timedatectl set-timezone Asia/Seoul

# 메모리가 부족해도 서버가 죽지 않게 디스크 2GB를 보조 메모리로
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
free -h   # Swap: 2.0Gi 확인
```

### 2-2. Docker 설치

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu   # sudo 없이 docker 명령 사용
exit                             # 권한 적용을 위해 재접속
```

```bash
ssh -i ~/keys/teokeopne.pem ubuntu@<EIP>
docker compose version   # 버전이 나오면 OK
```

### 2-3. 레포 clone · 배포용 `.env`

```bash
git clone https://github.com/2026-KW-HACKATHON/18_after-school-map-time.git ~/teokeopne
cd ~/teokeopne
git checkout develop
cp .env.example .env

# 값 생성 (출력값을 복사해 두기)
python3 -c "import secrets; print(secrets.token_urlsafe(50))"   # → SECRET_KEY
openssl rand -hex 24                                              # → DB 비밀번호 (URL에 넣어도 안전한 문자만)

nano .env
```

`.env`에서 바꿀 값 (나머지는 그대로):

```ini
SECRET_KEY=<생성한 값>
DEBUG=False
ALLOWED_HOSTS=<도메인>
CSRF_TRUSTED_ORIGINS=https://<도메인>

POSTGRES_PASSWORD=<생성한 DB 비밀번호>
DATABASE_URL=postgres://teokeopne:<생성한 DB 비밀번호>@db:5432/teokeopne

KAKAO_JAVASCRIPT_KEY=<JS 키>
KAKAO_REST_API_KEY=<REST 키>

DOMAIN=<도메인>          # 예: teokeopne.duckdns.org (https:// 없이)
NGINX_CONF=http          # 4단계에서 https로 바꿈
IMAGE_TAG=latest
```

> 이 `.env`는 **서버에만** 존재합니다. 서버에서 레포의 추적 파일(`.env` 제외)을 직접 고치지 마세요 — 자동 배포의 `git pull`이 충돌합니다.

---

## 3. 도메인 연결

**DuckDNS (무료)**
1. https://www.duckdns.org 에 로그인 → 서브도메인 입력(예: `teokeopne`) → **add domain**
2. `current ip` 칸에 `<EIP>` 입력 → **update ip**
3. 도메인 = `teokeopne.duckdns.org`

**유료 도메인**: 도메인 업체 DNS 설정에서 **A 레코드** `@` (또는 `www`) → `<EIP>`

확인 (몇 분 걸릴 수 있음):

```bash
nslookup <도메인>   # Address가 <EIP>면 OK
```

---

## 4. 첫 기동 → 인증서 발급 → HTTPS 전환

인증서가 없으면 HTTPS 설정의 nginx가 시작되지 않으므로, **HTTP 설정으로 먼저 띄워서 인증서를 받은 뒤 HTTPS로 바꿉니다.**

### 4-1. HTTP로 첫 기동

첫 배포는 Docker Hub에 이미지가 아직 없을 수 있으므로 서버에서 직접 빌드합니다.

```bash
cd ~/teokeopne
sudo mkdir -p /var/www/certbot
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec -T web python manage.py migrate --noinput
docker compose -f docker-compose.prod.yml exec -T web python manage.py collectstatic --noinput
docker compose -f docker-compose.prod.yml ps        # nginx, web, db 모두 Up
curl -i http://<도메인>/health/                     # 200 {"status": "ok", "db": true}
```

### 4-2. 인증서 발급 (certbot, webroot 방식)

```bash
sudo snap install --classic certbot
sudo ln -sf /snap/bin/certbot /usr/bin/certbot

sudo certbot certonly --webroot -w /var/www/certbot \
  -d <도메인> --email <팀장 이메일> --agree-tos --no-eff-email
# "Successfully received certificate" 가 나오면 성공
```

### 4-3. HTTPS 설정으로 전환

```bash
sed -i 's/^NGINX_CONF=.*/NGINX_CONF=https/' .env
docker compose -f docker-compose.prod.yml up -d nginx   # 바뀐 설정으로 nginx 재생성
curl -i https://<도메인>/health/                         # 200
curl -I http://<도메인>/                                 # 301 → https
```

### 4-4. 인증서 자동 갱신 (90일마다 만료)

certbot이 설치될 때 자동 갱신 타이머가 같이 켜집니다. 갱신된 인증서를 nginx가 다시 읽도록 hook만 추가합니다.

```bash
sudo tee /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh > /dev/null <<'EOF'
#!/bin/sh
docker compose -f /home/ubuntu/teokeopne/docker-compose.prod.yml exec -T nginx nginx -s reload
EOF
sudo chmod +x /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh

sudo certbot renew --dry-run   # "Congratulations, all simulated renewals succeeded" 확인
```

### 4-5. 카카오 개발자센터에 배포 도메인 등록

내 애플리케이션 → 플랫폼 → Web → 사이트 도메인에 `https://<도메인>` 추가. (안 하면 배포 사이트에서 지도가 안 뜸)

---

## 5. GitHub Secrets 등록 · 자동 배포 켜기

### 5-1. Docker Hub

1. https://hub.docker.com → Account settings → **Personal access tokens** → Generate (권한: Read & Write)
2. 저장소 `cjs1004ounds/teokeopne`는 첫 push 때 자동 생성됩니다. **Public**이어야 서버가 로그인 없이 pull 할 수 있습니다. (Private로 하려면 서버에서 `docker login` 필요)

### 5-2. GitHub Secrets

레포 → Settings → Secrets and variables → Actions → **New repository secret**

| 이름 | 값 |
| --- | --- |
| `DOCKER_USERNAME` | `cjs1004ounds` |
| `DOCKER_PASSWORD` | 5-1에서 만든 액세스 토큰 |
| `EC2_HOST` | `<EIP>` |
| `EC2_KEY` | `.pem` 파일 내용 **전체** (`-----BEGIN ...` 부터 `-----END ...-----` 까지) |

### 5-3. 수동 배포로 확인

레포 → Actions → **Deploy to EC2** → Run workflow (branch: `develop`) → 모든 단계 초록불 확인.

### 5-4. 자동 배포 켜기

`.github/workflows/deploy.yml`의 `push:` 트리거 주석을 풀고 PR로 머지합니다. 이후로는 **`develop`에 머지 = 자동 배포**입니다.

```yaml
on:
  workflow_dispatch:

  push:
    branches:
      - develop
```

---

## 6. 백업 · 최종 점검

### 6-1. DB 백업 cron (매일 새벽 4시, 7일치 보관)

```bash
cd ~/teokeopne
./scripts/backup_db.sh        # 한 번 직접 실행해서 backups/에 파일이 생기는지 확인
crontab -e                    # 처음이면 편집기 선택: 1 (nano)
```

맨 아래에 추가:

```
0 4 * * * /home/ubuntu/teokeopne/scripts/backup_db.sh >> /home/ubuntu/teokeopne/backups/backup.log 2>&1
```

### 6-2. 제보 사진(media) 백업 — 전시(10/11~13) 전에 꼭

```bash
cd ~/teokeopne && mkdir -p backups
docker run --rm -v teokeopne-prod_media_volume:/media:ro -v "$PWD/backups":/backup alpine \
  tar czf /backup/media_$(date +%F).tar.gz -C /media .
```

서버가 통째로 망가질 때를 대비해 내 PC로도 복사 (내 PC의 Git Bash에서):

```bash
scp -i ~/keys/teokeopne.pem "ubuntu@<EIP>:~/teokeopne/backups/*" ./teokeopne-backups/
```

### 6-3. 최종 점검 체크리스트

- [ ] `https://<도메인>/health/` → 200, `http://` 는 https로 리다이렉트
- [ ] 폰(LTE)으로 접속해서 화면·지도가 뜬다
- [ ] 폰 사진(3~8MB) 업로드가 413 없이 된다
- [ ] `DEBUG=False` (없는 주소 접속 시 노란 에러 화면이 아닌 404 페이지)
- [ ] 외부에서 5432 포트 접속 불가 (보안 그룹에 없음)
- [ ] `sudo certbot renew --dry-run` 성공
- [ ] `sudo reboot` 후 1~2분 뒤 사이트가 자동으로 다시 뜬다 (`restart: unless-stopped`)
- [ ] 백업 파일이 `backups/`에 매일 생긴다
- [ ] `.env`, `*.pem`, API 키가 커밋 이력에 없다 (`git log -p | grep -i "KAKAO\|SECRET"` 로 재확인)

---

## 7. 문제 해결

| 증상 | 확인 · 해결 |
| --- | --- |
| 사이트가 안 뜸 | `docker compose -f docker-compose.prod.yml ps` → 죽은 컨테이너 확인 → `... logs --tail 100 <서비스>` |
| **502 Bad Gateway** | web(gunicorn)이 죽음 → `logs web`. 주로 `.env` 오타, DB 비밀번호 불일치 |
| **400 Bad Request** | `ALLOWED_HOSTS`에 도메인이 없음 → `.env` 수정 후 `up -d` |
| **403 CSRF** (폼 제출 시) | `CSRF_TRUSTED_ORIGINS=https://<도메인>` 확인 |
| **413** | 10MB 초과 사진. 한도 변경은 `nginx/snippets/app.conf`와 `settings.py` 둘 다 |
| nginx가 계속 재시작 | HTTPS 설정인데 인증서가 없음 → `.env`를 `NGINX_CONF=http`로 되돌리고 `up -d nginx` → 4-2부터 |
| CSS가 안 먹음 | `exec -T web python manage.py collectstatic --noinput` |
| 디스크 부족 | `df -h`, `docker system df` → `docker image prune -af` (안 쓰는 이미지 전부 삭제) |
| DB 비밀번호를 바꿨더니 접속 불가 | Postgres는 **볼륨이 처음 만들어질 때만** 비밀번호를 설정함. 운영 중엔 바꾸지 말 것 |

**로그 보기**

```bash
cd ~/teokeopne
docker compose -f docker-compose.prod.yml logs -f --tail 100 web     # Ctrl+C로 종료
```

**롤백 (이전 버전으로 되돌리기)**

배포마다 Docker Hub에 `latest`와 **커밋 SHA 태그**가 같이 올라갑니다.

```bash
cd ~/teokeopne
# 되돌릴 커밋 SHA 확인: GitHub 커밋 목록 또는 Docker Hub Tags 탭
sed -i 's/^IMAGE_TAG=.*/IMAGE_TAG=<이전 커밋 SHA 40자리>/' .env
docker compose -f docker-compose.prod.yml pull web
docker compose -f docker-compose.prod.yml up -d web
# 문제 해결 후 원래대로: IMAGE_TAG=latest 로 바꾸고 다시 pull / up -d
```

> ⚠️ 롤백 중에는 자동 배포가 `latest`를 pull 해도 `IMAGE_TAG`가 SHA로 고정돼 있어 반영되지 않습니다. 꼭 `latest`로 되돌려 두세요.

**DB 복원**

```bash
gunzip -c backups/<파일>.sql.gz | docker compose -f docker-compose.prod.yml exec -T db psql -U teokeopne -d teokeopne
```
