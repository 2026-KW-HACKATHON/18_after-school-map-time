# 제3자 소프트웨어·서비스 고지 (Third-Party Notices)

턱없네(18조 방과 후 지도타임)는 아래 오픈소스와 외부 서비스를 사용합니다. 팀이 작성한 코드는 [MIT License](LICENSE)이며, 아래 구성요소에는 MIT가 적용되지 않습니다.
각 구성요소의 저작권은 원저작자에게 있으며, 각자의 라이선스·약관을 따릅니다.
버전은 `requirements.txt`·`Dockerfile`·`docker-compose*.yml`·`.github/workflows/`에 고정된 값입니다 (2026-10-08 기준).

## 라이선스를 지키는 방법

| 항목 | 이 프로젝트가 하는 일 |
| --- | --- |
| 수정하지 않고 사용 | 아래 라이브러리는 모두 `pip`·Docker 공식 배포본을 **수정 없이** 씁니다. 레포에 다른 프로젝트의 소스 코드를 복사해 넣지 않았습니다 (대회 규정). |
| 라이선스 원문 포함 | 서버 이미지(`cjs1004ounds/teokeopne`)는 `pip install`로 만들어지며, 각 패키지의 라이선스·저작권 표시·NOTICE 파일이 이미지 안 `/usr/local/lib/python3.12/site-packages/<패키지>-<버전>.dist-info/`에 **원문 그대로** 들어 있습니다. 지우거나 고치지 않습니다. |
| 저작권 표시 유지 | 이 문서와 README의 「오픈소스 / 출처」에 이름·라이선스·출처를 밝힙니다. |
| LGPL 구성요소 | `psycopg2-binary`, `pi-heif` 바이너리에 포함된 `libheif`·`libde265`, `opencv-python-headless` 바이너리에 포함된 LGPL 라이브러리는 **수정 없이 별도 공유 라이브러리로** 사용합니다. 원본 소스는 아래 링크에서 받을 수 있고, `requirements.txt`의 버전을 바꿔 다시 빌드하면 누구나 해당 라이브러리를 다른 버전으로 교체할 수 있습니다 (`Dockerfile` 공개). |
| MPL-2.0 구성요소 | `certifi`는 수정 없이 사용하며 원본 소스 링크를 밝힙니다. |
| 웹폰트·브라우저 스크립트 | Pretendard(OFL-1.1)와 qrcode-generator(MIT)는 원본 그대로 CDN 주소로 불러옵니다(파일을 고치거나 다시 배포하지 않음). |
| 데이터·API | 외부 API·데이터는 각 서비스 약관과 이용 조건을 따르고, 공공데이터는 출처를 화면(장소 상세)과 문서에 표시합니다. |

## 1. Python 패키지 (`requirements.txt`)

| 패키지 | 버전 | 용도 | 라이선스 | 출처 |
| --- | --- | --- | --- | --- |
| Django | 5.2.17 | 웹 프레임워크 | BSD-3-Clause | https://www.djangoproject.com/ |
| asgiref | 3.12.1 | Django 의존성 | BSD-3-Clause | https://github.com/django/asgiref |
| sqlparse | 0.6.0 | Django 의존성 | BSD-3-Clause | https://github.com/andialbrecht/sqlparse |
| tzdata | 2026.4 | 시간대 데이터 | Apache-2.0 | https://github.com/python/tzdata |
| djangorestframework | 3.18.1 | JSON API | BSD-3-Clause | https://www.django-rest-framework.org/ |
| django-allauth | 65.19.5 | 카카오 로그인 | MIT | https://allauth.org/ |
| PyJWT | 2.15.1 | allauth 의존성 (토큰) | MIT | https://github.com/jpadilla/pyjwt |
| cryptography | 50.0.1 | PyJWT 서명 검증 | Apache-2.0 OR BSD-3-Clause | https://cryptography.io/ |
| cffi | 2.1.1 | cryptography 의존성 | MIT-0 | https://github.com/python-cffi/cffi |
| pycparser | 3.0 | cffi 의존성 | BSD-3-Clause | https://github.com/eliben/pycparser |
| oauthlib | 3.3.1 | allauth 의존성 (OAuth2) | BSD-3-Clause | https://github.com/oauthlib/oauthlib |
| python-dotenv | 1.2.3 | `.env` 읽기 | BSD-3-Clause | https://github.com/theskumar/python-dotenv |
| dj-database-url | 3.1.2 | DB 주소 해석 | BSD-3-Clause | https://github.com/jazzband/dj-database-url |
| psycopg2-binary | 2.9.13 | PostgreSQL 드라이버 | LGPL-3.0-or-later (예외 조항 포함) | https://www.psycopg.org/ · 소스 https://github.com/psycopg/psycopg2 |
| gunicorn | 26.2.0 | WSGI 서버 | MIT | https://gunicorn.org/ |
| requests | 2.34.2 | 외부 API 호출 (카카오·Gemini·공공데이터) | Apache-2.0 | https://requests.readthedocs.io/ |
| pillow | 12.3.0 | 이미지 처리 | MIT-CMU | https://python-pillow.org/ |
| opencv-python-headless | 4.14.0.94 | 사진 속 얼굴 자동 가림 | Apache-2.0 | https://github.com/opencv/opencv-python |
| numpy | 2.3.5 | OpenCV 이미지 배열 | BSD-3-Clause | https://numpy.org/ |
| pi-heif | 1.4.0 | 아이폰 HEIC 사진 읽기 | BSD-3-Clause (바이너리 휠은 LGPL-3.0) | https://github.com/bigcat88/pillow_heif |

`pip`이 함께 설치하는 하위 패키지:

| 패키지 | 용도 | 라이선스 | 출처 |
| --- | --- | --- | --- |
| urllib3 | requests 의존성 | MIT | https://github.com/urllib3/urllib3 |
| idna | requests 의존성 | BSD-3-Clause | https://github.com/kjd/idna |
| charset-normalizer | requests 의존성 | MIT | https://github.com/jawah/charset_normalizer |
| certifi | requests 의존성 (인증서 묶음) | MPL-2.0 | https://github.com/certifi/python-certifi |

### 패키지 안에 함께 들어 있는 라이브러리 (바이너리 휠)

| 들어 있는 패키지 | 구성요소 | 라이선스 | 비고 |
| --- | --- | --- | --- |
| psycopg2-binary | libpq, OpenSSL | PostgreSQL License, Apache-2.0 | 패키지의 `psycopg2_binary.libs` |
| pi-heif | libheif, libde265 | LGPL-3.0 | 원문: `pi_heif-*.dist-info/licenses/LICENSES_bundled.txt` · 소스 https://github.com/strukturag/libheif , https://github.com/strukturag/libde265 |
| opencv-python-headless | OpenCV 및 포함 라이브러리(libvpx, FFmpeg 등) | Apache-2.0, BSD, LGPL-2.1 등 | 원문: `opencv_python_headless-*.dist-info/LICENSE-3RD-PARTY.txt` |
| opencv-python-headless | 정면 얼굴 검출 모델 `haarcascade_frontalface_default.xml` | Intel License Agreement (BSD 계열) | 패키지 안 파일을 **읽기만** 함 (`core/images.py`), 레포에 복사하지 않음 |
| numpy | OpenBLAS, (리눅스 휠) libgfortran | BSD-3-Clause, GPL-3.0 + GCC Runtime Library Exception | 원문: `numpy-*.dist-info/LICENSE.txt` |

## 2. 브라우저에서 불러오는 리소스 (CDN, 수정 없이 링크)

| 이름 | 버전 | 용도 | 라이선스 | 출처 |
| --- | --- | --- | --- | --- |
| Pretendard | 1.3.9 | 웹폰트 | SIL Open Font License 1.1 | https://github.com/orioncactus/pretendard (jsDelivr) |
| qrcode-generator | 1.4.4 | 안내 쪽지·전시 포스터 QR 코드 | MIT | https://github.com/kazuhikoarase/qrcode-generator (cdnjs) |
| 카카오맵 JavaScript SDK | v2 | 지도 | 카카오 API 이용약관 (오픈소스 아님) | https://apis.map.kakao.com/ |

## 3. 서버·컨테이너·배포 도구

| 이름 | 용도 | 라이선스 | 출처 |
| --- | --- | --- | --- |
| Python (`python:3.12-slim` 이미지) | 서버 실행 환경 | PSF License 2.0 (이미지 안 Debian 구성요소는 각 라이선스) | https://hub.docker.com/_/python |
| PostgreSQL (`postgres:16` 이미지) | 데이터베이스 | PostgreSQL License | https://www.postgresql.org/ |
| Nginx (`nginx:1.30-alpine` 이미지) | 리버스 프록시·HTTPS | BSD-2-Clause | https://nginx.org/ |
| Docker / Docker Compose | 컨테이너 실행 | Apache-2.0 | https://www.docker.com/ |
| Certbot | HTTPS 인증서 발급 (서버에 설치) | Apache-2.0 | https://certbot.eff.org/ |

## 4. CI/CD (GitHub Actions)

| 이름 | 버전 | 라이선스 |
| --- | --- | --- |
| actions/checkout, actions/setup-python, actions/setup-node | v7 | MIT |
| docker/login-action | v4 | Apache-2.0 |
| appleboy/ssh-action | v1.2.5 | MIT |
| Node.js (화면 JS 테스트 실행, 내장 테스트 러너) | 22 | MIT |

## 5. 외부 서비스·API·데이터 (오픈소스 아님, 각 약관을 따름)

| 이름 | 용도 | 약관·이용 조건 |
| --- | --- | --- |
| 카카오맵 API · 로컬 API · 카카오 로그인 | 지도, 주소·장소 검색, 로그인 | [카카오 개발자 운영정책·이용약관](https://developers.kakao.com/terms/latest/ko/site-policies) |
| Google Gemini API (유료 등급) | 제보 사진·설명에서 접근성 항목 후보 추출 (운영자 검토 보조, 주민 'AI로 항목 채우기') | [Gemini API 추가 약관](https://ai.google.dev/gemini-api/terms) — 유료 등급은 입력·출력을 제품 개선에 쓰지 않음. 결과는 운영자·주민이 확인하며 자동 승인하지 않음 |
| OpenAI API (선택, 기본 사용 안 함) | 위와 같은 용도의 대체 제공자 | [OpenAI 이용약관](https://openai.com/policies/) |
| 공공데이터포털 「한국사회보장정보원_장애인편의시설 현황」 | 월계동 공공·업무시설 초기 데이터 (`places/data/public/`) | 이용허락범위 제한 없음 · [데이터 페이지](https://www.data.go.kr/data/15092317/openapi.do) · 출처: 공공데이터포털(한국사회보장정보원) |
| DuckDNS | 도메인 (`teokeopne.duckdns.org`) | https://www.duckdns.org/ |
| Let's Encrypt | HTTPS 인증서 | [Subscriber Agreement](https://letsencrypt.org/repository/) |
| AWS EC2 · Docker Hub · GitHub | 서버·이미지 저장소·코드 저장소 | 각 서비스 약관 |

## 6. 개발 도구

- Claude Code (Anthropic) — AI 코딩 도우미. 대회 규정상 AI 도구 사용이 허용되며, 결과물은 팀원 전원이 검토·이해한 뒤 반영합니다.
