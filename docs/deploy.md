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
| 2 | 서버 초기 설정 (swap, Docker, 로그 제한, fail2ban, 레포 clone, `.env`) | EC2 (SSH) |
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
| AMI | **Ubuntu Server 26.04 LTS** |
| 인스턴스 유형 | **t3.small** (RAM 2GB). t3.micro(1GB, 프리티어)면 2단계 swap 필수 |
| 키 페어 | 새로 생성 → RSA, `.pem` → 다운로드한 파일은 **레포 밖**에 보관 (절대 커밋 금지). 이하 이 파일 위치를 `<키 파일 경로>`라고 부름 |
| 스토리지 | **30GB gp3** (Docker 이미지가 쌓이므로 여유 있게) |

**보안 그룹** (인바운드 규칙)

| 유형 | 포트 | 소스 | 이유 |
| --- | --- | --- | --- |
| SSH | 22 | 0.0.0.0/0 | 서버 접속 + GitHub Actions 배포 (**키 인증 전용 + fail2ban**) |
| HTTP | 80 | 0.0.0.0/0 | 인증서 발급·https 리다이렉트 |
| HTTPS | 443 | 0.0.0.0/0 | 서비스 |

> ❌ 5432(PostgreSQL)는 **열지 않습니다.** DB는 서버 안의 web 컨테이너만 접근합니다.
>
> ⚠️ GitHub Actions는 실행할 때마다 접속 IP가 바뀌어서, 22번을 "내 IP"로 막으면 자동 배포가 서버에 접속하지 못합니다. 그래서 22번은 `0.0.0.0/0`으로 열고, 대신 **키 인증 전용**(비밀번호 로그인 불가)과 **fail2ban**(2-3단계, 로그인 실패가 반복되는 IP 자동 차단)으로 막습니다.

**탄력적 IP**: EC2 → 탄력적 IP → 할당 → 방금 만든 인스턴스에 **연결**. (재시작해도 IP가 안 바뀜) 이 IP를 이하 `<EIP>`라고 부릅니다.

---

## 2. 서버 초기 설정 (SSH)

내 PC에서 접속합니다. `<키 파일 경로>`는 1단계에서 받은 `.pem` 파일의 위치입니다.

**Git Bash / macOS / Linux**

```bash
chmod 400 "<키 파일 경로>"
ssh -i "<키 파일 경로>" ubuntu@<EIP>
```

**Windows cmd / PowerShell** — Windows에 내장된 ssh는 `chmod`가 통하지 않고, 키 파일을 다른 계정도 읽을 수 있으면 `UNPROTECTED PRIVATE KEY FILE` 에러로 접속을 거부합니다. `icacls`로 **내 계정만 읽을 수 있게** 권한을 바꿉니다.

```powershell
# PowerShell
icacls "<키 파일 경로>" /inheritance:r                      # 상위 폴더에서 물려받은 권한 제거
icacls "<키 파일 경로>" /grant:r "$($env:USERNAME):(R)"     # 내 계정에만 읽기 권한
ssh -i "<키 파일 경로>" ubuntu@<EIP>
```

```bat
:: cmd
icacls "<키 파일 경로>" /inheritance:r
icacls "<키 파일 경로>" /grant:r "%USERNAME%:(R)"
ssh -i "<키 파일 경로>" ubuntu@<EIP>
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
ssh -i "<키 파일 경로>" ubuntu@<EIP>
docker compose version   # 버전이 나오면 OK
```

### 2-3. Docker 로그 용량 제한 · fail2ban

**Docker 로그 용량 제한** — 컨테이너 로그는 기본적으로 끝없이 쌓여서, 전시 기간처럼 오래 켜 두면 디스크를 가득 채울 수 있습니다. 컨테이너마다 10MB × 3개(최대 30MB)만 남기도록 제한합니다.

```bash
sudo tee /etc/docker/daemon.json > /dev/null <<'EOF'
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "3" }
}
EOF
sudo systemctl restart docker
docker info --format '{{.LoggingDriver}}'   # json-file 이 나오면 OK
```

> 이 설정은 **새로 만들어지는 컨테이너부터** 적용됩니다. 이미 서비스가 떠 있는 서버라면 한 번 재생성하세요:
> `cd ~/teokeopne && docker compose -f docker-compose.prod.yml up -d --force-recreate`

**fail2ban** — SSH(22)를 전체에 열어 두므로(1단계), 로그인 실패를 반복하는 IP를 자동으로 차단합니다.

```bash
# 키 인증 전용인지 확인 → "passwordauthentication no" 면 OK (EC2 Ubuntu 기본값)
sudo sshd -T | grep -i '^passwordauthentication'

sudo apt-get update
sudo apt-get install -y fail2ban
sudo systemctl enable --now fail2ban
sudo fail2ban-client status sshd   # "Status for the jail: sshd" 가 나오면 SSH 감시 중
```

### 2-4. 레포 clone · 배포용 `.env`

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
docker compose -f docker-compose.prod.yml exec -T web python manage.py seed_base   # 지역·접근성 필드 정의 (처음 한 번)
docker compose -f docker-compose.prod.yml exec -T web python manage.py load_rules  # 판정 규칙 (처음 한 번, 규칙 파일을 바꿨을 때)
# 관리자 계정은 `createsuperuser`로 만들고, https://<도메인>/ops/ (운영자 화면)와 /admin/ 에서 로그인
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

> ⚠️ **새 SSH 세션에서 실행하세요.** 셸에 `.env` 값을 `export`해 둔 상태(예: `set -a; source .env`, `export $(cat .env | xargs)`)라면,
> docker compose는 `.env` 파일보다 **셸 환경변수를 우선**합니다. 그러면 아래에서 `.env`를 `NGINX_CONF=https`로 바꿔도 셸에 남은 예전 값(`http`)으로 nginx가 뜹니다.
> `exit` 후 다시 접속하거나, `echo "$NGINX_CONF"`가 빈 줄인지 확인한 뒤 진행하세요.

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

[카카오 개발자센터](https://developers.kakao.com) → 앱 선택 → **앱 > 플랫폼 키 > JavaScript 키 > JavaScript SDK 도메인**에 `https://<도메인>` 추가.
개발용 `http://localhost:8000`은 그대로 둡니다. (등록하지 않으면 배포 사이트에서 지도가 안 뜸)

**카카오 로그인 Redirect URI**: 카카오 로그인 설정의 Redirect URI에 아래 두 개를 등록합니다. (없으면 로그인 시 `KOE006` 에러)

```
http://localhost:8000/accounts/kakao/login/callback/
https://<도메인>/accounts/kakao/login/callback/
```

동의 항목은 **닉네임**만 켭니다. (이메일·전화번호는 받지 않음) Client Secret을 '사용함'으로 켰다면 서버 `.env`의 `KAKAO_CLIENT_SECRET`에도 넣습니다.

---

## 5. GitHub Secrets 등록 · 자동 배포

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

### 5-4. 자동 배포 (켜져 있음)

`.github/workflows/deploy.yml`은 `push`(develop) 트리거가 켜져 있어서 **`develop`에 머지 = 자동 배포**입니다. 진행 상황은 Actions 탭에서 확인합니다.

> 서버를 처음부터 새로 구축하는 중이라면(1~5-3단계 진행 중) `develop` 머지 때 배포가 실패합니다.
> 그동안은 `deploy.yml`의 `push:` 트리거 3줄을 잠시 주석 처리하고, 5-3 수동 배포가 성공한 뒤 다시 켜세요.

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
scp -i "<키 파일 경로>" "ubuntu@<EIP>:~/teokeopne/backups/*" ./teokeopne-backups/
```

### 6-3. 최종 점검 체크리스트

- [ ] `https://<도메인>/health/` → 200, `http://` 는 https로 리다이렉트
- [ ] 폰(LTE)으로 접속해서 화면·지도가 뜬다
- [ ] 폰 사진(3~8MB) 업로드가 413 없이 된다
- [ ] `DEBUG=False` (없는 주소 접속 시 노란 에러 화면이 아닌 404 페이지)
- [ ] 외부에서 5432 포트 접속 불가 (보안 그룹에 없음)
- [ ] SSH는 키 인증 전용, `sudo fail2ban-client status sshd` 동작 중
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

> ⚠️ **DB 마이그레이션은 되돌리지 않습니다** (`migrate <앱> <이전 번호>` 금지).
> 롤백은 위처럼 **이미지(코드)만** 이전 버전으로 바꿉니다. 우리 마이그레이션은 칼럼 추가·제약 완화처럼
> 이전 코드가 새 DB에서도 돌아가게 만들기 때문에 DB는 그대로 두면 됩니다 (새 마이그레이션도 이 원칙을 지킵니다).
> 반대로 DB를 되돌리면 새 기능으로 들어온 데이터(예: 출입구 없이 시설만 있는 제보) 때문에
> 이전 제약조건을 다시 걸지 못해 실패합니다. 데이터 자체가 꼬였다면 아래 **DB 복원**으로 백업 시점으로 돌아갑니다.

**DB 복원**

```bash
gunzip -c backups/<파일>.sql.gz | docker compose -f docker-compose.prod.yml exec -T db psql -U teokeopne -d teokeopne
```
