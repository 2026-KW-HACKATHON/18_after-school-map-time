# Python 3.12 slim 이미지 기반 (full 이미지보다 작아서 빌드·배포가 빠름)
FROM python:3.12-slim

# PYTHONUNBUFFERED: 로그를 버퍼링 없이 바로 출력 (docker compose logs에서 즉시 보임)
# PYTHONDONTWRITEBYTECODE: .pyc 파일을 만들지 않음 (볼륨 마운트 시 호스트에 찌꺼기 안 남김)
# PIP_*: pip 캐시를 이미지에 남기지 않고, 버전 체크 경고를 끔
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 컨테이너 안 작업 디렉토리
WORKDIR /app

# 의존성 먼저 복사·설치 (requirements.txt가 안 바뀌면 이 레이어는 캐시 재사용 → 재빌드가 빠름)
# psycopg2-binary / pillow 는 미리 빌드된 휠로 설치되므로 gcc, libpq-dev 같은 빌드 도구는 설치하지 않음
COPY requirements.txt .
RUN pip install -r requirements.txt

# 프로젝트 전체 복사 (.dockerignore에 적힌 .env·문서 등은 제외됨)
COPY . .

EXPOSE 8000

# 배포 실행 명령: gunicorn
#   --workers 3  : 요청을 동시에 처리할 프로세스 수 (t3.small 2GB 기준 3개면 충분)
#   --timeout 60 : AI 사진 판별처럼 느린 외부 API를 기다릴 수 있게 기본 30초 → 60초
# 개발 환경에서는 docker-compose.yml이 runserver로 덮어씀
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "60"]
