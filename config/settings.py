"""
턱없네 Django 설정.
값은 전부 .env 에서 읽습니다. (.env.example 참고, 새 변수를 추가하면 .env.example과 README도 같이 갱신)
"""

import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# .env 읽기 (이미 환경변수로 들어온 값이 있으면 그걸 우선 → CI·배포 서버에서 덮어쓰기 가능)
load_dotenv(BASE_DIR / ".env")


def env_list(name, default=""):
    """콤마로 구분된 환경변수를 리스트로 (빈 값은 제외)"""
    return [v.strip() for v in os.getenv(name, default).split(",") if v.strip()]


# ── 기본 ──
# 문자열 "True"일 때만 켜짐. 값이 없으면 False → 배포에서 실수로 디버그 화면이 노출되는 일 방지
DEBUG = os.getenv("DEBUG", "False") == "True"

# 비어 있으면 서버가 아예 안 뜨게 해서 바로 알 수 있게 함 (기본값으로 조용히 넘어가면 보안 사고)
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ImproperlyConfigured("SECRET_KEY 환경변수가 비어 있습니다. .env를 확인하세요. (생성 명령은 .env.example 참고)")

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1")
# HTTPS 도메인에서 POST(폼 제출·제보)가 403 나지 않도록 허용 목록 지정. 예: https://teokeopne.example.com
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")


# ── 앱 ──
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # DRF (지도 데이터는 JSON API로 제공)
    "rest_framework",

    # 카카오 로그인 (django-allauth)
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.kakao",

    # 우리 앱 (python manage.py startapp <앱이름> 후 여기에 추가)
    "core",      # 헬스체크, 홈, 공통 템플릿
    "accounts",  # 회원 (커스텀 User, 카카오 로그인)
    "places",    # 지역·건물·장소·출입구·접근성 필드 정의
    "reports",   # 제보(접근성 값의 출처)·확인
    "judgments", # 판정 규칙(데이터)·판정 엔진·판정 결과
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",  # allauth 필수
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],  # 전역 템플릿 (base.html 등)
        "APP_DIRS": True,                  # 각 앱의 templates/<앱>/ 도 찾음
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.kakao_keys",  # 모든 템플릿에서 {{ KAKAO_JAVASCRIPT_KEY }} 사용
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# ── DB ──
# DATABASE_URL 이 있으면 PostgreSQL, 없으면 SQLite (Docker 없이 로컬 실행·CI용 폴백)
if os.getenv("DATABASE_URL"):
    DATABASES = {"default": dj_database_url.parse(os.getenv("DATABASE_URL"))}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }


# ── 회원·로그인 ──
# 커스텀 User: 닉네임·가입일 규칙 등을 넣기 위해 프로젝트 초기에 지정 (나중에 바꾸면 DB를 다시 만들어야 함)
AUTH_USER_MODEL = "accounts.User"

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",            # 관리자 /admin/ 아이디·비밀번호 로그인
    "allauth.account.auth_backends.AuthenticationBackend",  # 카카오 로그인
]

LOGIN_URL = "account_login"
LOGIN_REDIRECT_URL = "/"
ACCOUNT_LOGOUT_REDIRECT_URL = "/"

# 일반 회원은 카카오 로그인만 사용 (아이디·비밀번호 가입/로그인 화면 없음)
SOCIALACCOUNT_ONLY = True
ACCOUNT_EMAIL_VERIFICATION = "none"
SOCIALACCOUNT_ADAPTER = "accounts.adapters.SocialAccountAdapter"
SOCIALACCOUNT_AUTO_SIGNUP = True       # 첫 카카오 로그인 때 추가 입력 없이 바로 가입
SOCIALACCOUNT_EMAIL_REQUIRED = False   # 이메일은 받지 않음 (동의 항목: 닉네임만)
SOCIALACCOUNT_STORE_TOKENS = False     # 카카오 액세스 토큰은 쓸 일이 없으므로 저장하지 않음
SOCIALACCOUNT_PROVIDERS = {
    "kakao": {
        # 카카오 개발자센터 앱 키. client_id = REST API 키, secret = 보안 > Client Secret (사용 안 하면 빈 값)
        "APPS": [
            {
                "client_id": os.getenv("KAKAO_REST_API_KEY", ""),
                "secret": os.getenv("KAKAO_CLIENT_SECRET", ""),
                "key": "",
            }
        ],
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# ── 언어·시간 ──
LANGUAGE_CODE = "ko-kr"
TIME_ZONE = "Asia/Seoul"
USE_I18N = True
USE_TZ = True


# ── 정적 파일 / 업로드 파일 ──
# 배포에서는 collectstatic 결과(staticfiles/)와 업로드(media/)를 nginx가 직접 서빙
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# 폰 사진(3~8MB)을 받기 위해 nginx client_max_body_size(10M)와 맞춤
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 요청 본문(파일 제외) 최대 크기
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 이보다 큰 업로드 파일은 메모리 대신 임시 파일로 처리

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ── 배포(HTTPS) 보안 설정: DEBUG=False일 때만 ──
if not DEBUG:
    # nginx가 HTTPS를 처리하고 web에는 http로 넘기므로, nginx가 붙여준 헤더로 "원래 https였음"을 판단
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    # 세션·CSRF 쿠키를 HTTPS에서만 전송
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    # http → https 리다이렉트는 nginx가 담당 (Django에서도 하면 인증서 발급 전 HTTP 설정에서 무한 리다이렉트)
    SECURE_SSL_REDIRECT = False
    # HSTS는 의도적으로 보류: 켜면 브라우저가 도메인을 한동안 https로만 접속해서,
    # 인증서 설정이 한 번 꼬이면 복구가 어려움. 배포가 안정된 뒤(본선 전) 켤지 결정.
    SECURE_HSTS_SECONDS = 0


# ── 로깅: 콘솔 출력 (docker compose logs web 으로 확인) ──
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "[{asctime}] {levelname} {name}: {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
}


# ── DRF (세션 인증: 같은 도메인의 템플릿 페이지에서 fetch로 호출) ──
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
}


# ── 외부 API 키 ──
KAKAO_JAVASCRIPT_KEY = os.getenv("KAKAO_JAVASCRIPT_KEY", "")  # 브라우저용: 템플릿에서 지도 SDK 로드
KAKAO_REST_API_KEY = os.getenv("KAKAO_REST_API_KEY", "")      # 서버 전용: 주소→좌표 등. 템플릿/JS로 절대 내보내지 않기
AI_VISION_API_KEY = os.getenv("AI_VISION_API_KEY", "")        # AI 사진 판별 (서비스 미정)
