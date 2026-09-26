#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────
# PostgreSQL 백업 스크립트 (배포 서버용)
#   db 컨테이너 안에서 pg_dump → backups/날짜_시간.sql.gz 로 저장
#   KEEP_DAYS(기본 7일)보다 오래된 백업은 자동 삭제
#
# 사용법 (레포 폴더 어디서 실행해도 됨):
#   ./scripts/backup_db.sh            # 7일치 보관
#   KEEP_DAYS=14 ./scripts/backup_db.sh
#
# cron 등록(매일 새벽 4시)은 docs/deploy.md 6단계 참고
# 복원: gunzip -c backups/<파일>.sql.gz | docker compose -f docker-compose.prod.yml exec -T db psql -U <유저> -d <DB이름>
# ─────────────────────────────────────────────────────────

# 명령 하나라도 실패하면 즉시 중단 (pipefail: pg_dump가 실패하면 gzip 성공이어도 실패로 처리)
set -euo pipefail

# 스크립트 위치 기준으로 레포 루트로 이동 → cron에서 실행해도 경로가 꼬이지 않음
cd "$(dirname "$0")/.."

KEEP_DAYS="${KEEP_DAYS:-7}"
BACKUP_DIR="backups"
COMPOSE="docker compose -f docker-compose.prod.yml"

# .env 에서 DB 이름·유저만 읽음 (없으면 compose 기본값과 같은 teokeopne)
POSTGRES_DB=$(grep -E '^POSTGRES_DB=' .env | cut -d= -f2- || true)
POSTGRES_USER=$(grep -E '^POSTGRES_USER=' .env | cut -d= -f2- || true)
POSTGRES_DB="${POSTGRES_DB:-teokeopne}"
POSTGRES_USER="${POSTGRES_USER:-teokeopne}"

mkdir -p "$BACKUP_DIR"
FILE="$BACKUP_DIR/$(date +%Y-%m-%d_%H%M).sql.gz"

echo "[backup] $POSTGRES_DB → $FILE"
# -T: cron처럼 터미널이 없는 환경에서도 동작 / --clean --if-exists: 복원 시 기존 테이블을 지우고 다시 만듦
$COMPOSE exec -T db pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists | gzip > "$FILE"

# 비어 있는 백업(=실패)이면 지우고 에러
if [ ! -s "$FILE" ]; then
    rm -f "$FILE"
    echo "[backup] 실패: 백업 파일이 비어 있습니다." >&2
    exit 1
fi
echo "[backup] 완료 ($(du -h "$FILE" | cut -f1))"

# 오래된 백업 정리
find "$BACKUP_DIR" -name '*.sql.gz' -mtime +"$KEEP_DAYS" -print -delete | sed 's/^/[backup] 오래된 백업 삭제: /'
