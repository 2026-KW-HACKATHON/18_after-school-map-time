# CLAUDE.md — 턱없네 (월계1동 접근성 지도 · 18조 방과 후 지도타임)

이 파일은 Claude Code가 이 레포에서 작업할 때 가장 먼저 읽는 안내서다.
세부 내용은 아래 `docs/context/` 문서에 있다. 작업 성격에 맞는 문서를 반드시 읽고 시작한다.

@docs/context/project.md
@docs/context/conventions.md
@docs/context/infra.md
@docs/context/setup-tasks.md

---

## 한눈에 보기

- **서비스 이름:** 턱없네
- **무엇:** 휠체어·유아차·보행 보조기 등 이동 조건별로 "이 가게 들어갈 수 있나?"에 답하는 월계1동 접근성 지도 웹서비스
- **대회:** 2026 광운대학교 해커톤 (노원구 월계1동 생활 밀착형 문제, 카테고리: 배리어프리 및 생활 편의)
- **스택:** Python · Django · DRF · 카카오맵 · PostgreSQL · Nginx · Gunicorn · Docker Compose · AWS EC2 · GitHub Actions
- **레포 규칙의 원본:** 팀장(강성훈)이 PM·인프라를 맡았던 피로그래밍 프로젝트 [Dopamine-Ledger](https://github.com/pirogramming/Dopamine-Ledger)
  → 규칙·Docker·CI 구조는 이 레포를 따르고, `conventions.md`의 "개선점"만 추가로 반영한다.

## 절대 규칙 (해커톤 규정에서 나온 것)

1. **다른 프로젝트의 코드를 복사하지 않는다.** Dopamine-Ledger에서는 *규칙·설정 방식·템플릿 구조*만 참고한다.
   모델·뷰·템플릿 등 앱 코드는 절대 가져오지 않는다. (해커톤 이전 작성 코드 사용 금지, 본인 보일러플레이트만 허용)
2. **시크릿은 절대 커밋하지 않는다.** 레포는 심사 시 public이 되고, 커밋 이력이 그대로 공개된다.
   `.env`, `*.pem`, API 키는 커밋 이력에 한 번이라도 들어가면 안 된다. 새 환경변수는 `.env.example`에 빈 값으로만 추가한다.
3. **커밋 이력이 심사 대상이다.** 작업은 의미 단위로 잘게 커밋하고 커밋 컨벤션(`<타입>: <내용>`, 한국어)을 지킨다.
4. **팀원 전원이 설명할 수 있어야 한다.** 설정 파일에는 "왜 이렇게 했는지" 한국어 주석을 단다. 과한 추상화·마법 같은 설정은 피한다.
5. **오픈소스를 쓰면 README의 "오픈소스 / 출처" 섹션에 기록한다.** (대회 규정)
6. **localhost 배포는 감점 요인이다.** 최종 결과물은 실제 도메인 + HTTPS로 접속 가능해야 한다.

## 지금 단계의 작업 범위

- 현재 우선순위는 **레포 규칙 + Docker 개발 환경 + 배포 인프라**다. (`setup-tasks.md` 참고)
- 인프라 작업 중에는 **도메인 모델(장소·제보 등)이나 기능 코드를 만들지 않는다.** 앱 구조·ERD는 팀이 따로 설계 중이다.
- 아래 "미정 사항"에 해당하는 결정이 필요하면 **추측해서 진행하지 말고 사용자에게 먼저 묻는다.**

## 결정된 사항 (2026-09-26)

| 항목 | 결정 |
|---|---|
| 지도 | **카카오맵** (구글 지도에서 변경). JS 키는 브라우저용, REST 키는 서버 전용 |
| 프론트엔드 방식 | Django Template + Vanilla JS, 지도 데이터는 DRF JSON API |
| Docker Hub 이미지 이름 | `cjs1004ounds/teokeopne` |
| 기능 코드 | 인프라 단계에서는 `core`(헬스체크·공통 템플릿)만 둔다. 도메인 앱은 팀 ERD 확정 + 운영진 확인 후 |

## 미정 사항 (진행 전 사용자 확인 필요)

| 항목 | 기본 제안 | 비고 |
|---|---|---|
| 도메인 | 미정 | DuckDNS(무료) 또는 유료 도메인. HTTPS 필수 |
| 이미지(제보 사진) 저장 | EC2 로컬 media 볼륨 | 여유 있으면 S3 |
| 위치 데이터 | 위도/경도 `DecimalField` | 반경 검색이 꼭 필요하면 PostGIS 이미지로 교체 |
| AI 사진 판별 API | 미정 (윤재석 검토 중) | `.env.example`에 자리만 만들어 둠 |
| PR 승인 인원 | Dopamine과 동일하게 2명 | 본선 무박 2일에는 1명으로 완화 권장 |

## 작업 방식

- 기존 파일이 있으면 **덮어쓰기 전에 먼저 읽고**, 무엇을 바꿀지 요약한 뒤 수정한다.
- 작업 단위마다 커밋한다. **`git push`와 PR 머지는 사용자에게 확인받은 뒤에만** 한다.
- 설정을 바꾼 뒤에는 가능하면 실제로 실행해서 확인한다 (`docker compose up --build`, `/health/` 응답 등).
- 사용자는 Windows(Git Bash) 환경일 수 있다. 경로에 한글을 쓰지 않고, 셸 스크립트는 LF 줄바꿈을 유지한다.
- 사용자와의 대화·문서·주석은 한국어로 작성한다.

## 자주 쓰는 명령어

```bash
# 개발 환경
docker compose up --build
docker compose exec web python manage.py makemigrations
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py test
docker compose exec web bash

# 배포 구성 로컬 검증
docker compose -f docker-compose.prod.yml up --build
```
