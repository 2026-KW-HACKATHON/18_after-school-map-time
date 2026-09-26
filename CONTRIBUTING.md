# 🤝 기여 가이드 (CONTRIBUTING)

턱없네(18조 방과 후 지도타임) 팀의 협업 규칙입니다. **작업 시작 전에 꼭 읽어주세요.**

> 이 레포는 심사 시점에 public으로 공개되고, **커밋 이력도 심사에 반영**됩니다.
> 커밋 메시지·PR 설명을 다른 사람이 읽는다고 생각하고 작성해주세요.

---

## 📢 소통

- **실시간 소통:** 디스코드
- **공지·문서:** 노션
- **정기 회의:** 매일 1회 (짧게 — 어제 한 것 / 오늘 할 것 / 막힌 것)
- **막히면:** 30분 이상 혼자 헤매지 말고 디스코드에 공유. 팀장이 지원합니다.

---

## 🌿 브랜치 전략

```
main        ← 최종 제출/릴리스용. 직접 push 금지.
 └ develop  ← 통합 브랜치 (기본 브랜치). feature가 여기로 머지됨. push 시 EC2 자동 배포(설정 후).
    └ feature/기능명   ← 개인 작업 브랜치. 이슈 단위로 생성.
```

- **`main`, `develop` 직접 push 금지.** 모든 변경은 PR을 통해 들어옵니다.
- 작업은 항상 최신 `develop`에서 브랜치를 따서 시작합니다.
- `develop`에 머지되면 곧바로 실제 서버에 배포됩니다. **`develop`은 항상 실행 가능한 상태로 유지하세요.**

```bash
git checkout develop
git pull origin develop
git checkout -b feature/place-marker
```

### 브랜치 이름 규칙

- `feature/기능명` — 새 기능 (예: `feature/place-marker`)
- `fix/버그명` — 버그 수정 (예: `fix/marker-color`)
- `docs/문서명` — 문서 (예: `docs/readme`)
- `chore/작업명` — 설정·인프라 (예: `chore/nginx-https`)

> **이슈 단위로 브랜치를 만듭니다.** 이슈 하나 = 브랜치 하나 = PR 하나.

---

## 🎫 이슈 관리

- **이슈는 작게 세분화합니다.** "지도 만들기"(X) → "지도에 장소 마커 표시"(O)
- 이슈 하나는 **1~2일 안에 끝낼 수 있는 크기**로.
- 작업 시작 전 이슈를 먼저 만들고(템플릿 5종 중 선택), 그 이슈 번호로 브랜치·PR을 연결합니다.

**이슈 제목 예시**

- `[places] 장소 목록 API`
- `[places] 조건별 판정 함수 + 단위 테스트`
- `[reports] 제보 폼 - 사진 업로드`

---

## ✍️ 커밋 컨벤션

`<타입>: <내용>` 형식으로, **한국어**로 작성합니다.

| 타입       | 용도                       |
| ---------- | -------------------------- |
| `feat`     | 새 기능                    |
| `fix`      | 버그 수정                  |
| `docs`     | 문서                       |
| `style`    | 코드 포맷 (기능 변화 없음) |
| `refactor` | 리팩터링                   |
| `test`     | 테스트 추가/수정           |
| `chore`    | 설정·빌드·인프라 등 잡무   |
| `design`   | UI·디자인 수정             |

```bash
git commit -m "feat: 장소 상세 API 추가"
git commit -m "fix: 경사로 있는 가게가 '어려움'으로 판정되는 오류 수정"
```

- **의미 단위로 잘게** 커밋합니다. "오늘 작업 전부"를 한 커밋에 몰지 않습니다.

---

## 🔀 Pull Request (PR)

1. 작업이 끝나면 `develop`을 대상으로 PR을 엽니다. (템플릿이 자동으로 채워집니다)
2. **최소 1명의 리뷰 승인** 후 머지합니다.
3. CI(GitHub Actions)가 실패한 PR은 머지하지 않습니다.
4. PR은 **이슈 단위**로 작게 유지합니다. (거대한 PR = 리뷰 지옥)
5. 리뷰어가 이해할 수 있도록 **핵심 로직엔 간단한 주석**을 답니다.

### PR 설명에 담을 것

- 무엇을 / 왜 바꿨는지 (2~3줄)
- 관련 이슈 번호 (`Closes #12`)
- 테스트 방법 (어떻게 확인했는지)
- (화면이면) 스크린샷

### 리뷰할 때

- 비난이 아니라 제안. "이거 왜 이렇게 했어요?"(X) → "여기 이렇게 하면 어떨까요?"(O)
- 사소한 것도 좋으니 **막힌 사람 없게 빨리 리뷰**합니다. 리뷰 대기가 병목이 되지 않도록.

---

## 🧪 코드 규칙

- **판정 로직(이동 조건별 가능 / 조건부 / 어려움 / 미확인)은 단위 테스트 필수.** 판정이 틀리면 서비스 신뢰가 무너집니다.
- 파생값(장소의 최종 판정, 신뢰도 등)은 **가능하면 저장하지 않고 계산**합니다. (저장값과 원본이 어긋나는 문제 원천 차단)
- **앱(폴더) 경계 = 기능 경계 = 담당자 경계.** 새 앱은 `startapp` 후 `config/settings.py`의 `INSTALLED_APPS`와 `config/urls.py`에 등록합니다.
- 모든 페이지는 `templates/base.html`을 `extends` 하고, 색·간격은 `static/css/common.css`의 CSS 변수를 씁니다.
- 외부 API(카카오, AI 판별) 호출은 뷰에 직접 쓰지 말고 앱의 `services.py`에 모읍니다.
- **카카오 REST API 키는 서버 전용.** 템플릿·JS로 내보내는 건 JavaScript 키뿐입니다.
- 마이그레이션 파일은 커밋합니다. 같은 앱의 모델을 여러 명이 동시에 고치면 충돌하니 모델 변경은 미리 공유합니다.
- 새 패키지는 `requirements.txt`에 **버전 고정 + 용도 주석**으로 추가합니다. 오픈소스를 쓰면 README "📚 오픈소스 / 출처"에도 기록합니다. (대회 규정)
- `.env`, 시크릿 키, `*.pem`, DB 파일 등은 **절대 커밋하지 않습니다.** 새 환경변수는 `.env.example`에 **빈 값으로만** 추가합니다.
- 커밋 전 로컬에서 한 번 실행해보고 올립니다. (`docker compose up`으로 안 깨지는지)

---

## ⚖️ 의사결정

- 논의는 함께, 하지만 **막히면 최종 결정은 PM(강성훈)이 책임지고 내립니다.**
- 방향성에서 벗어나지 않는 한, 각 담당자가 자기 파트의 세부는 자율적으로 결정합니다.

---

## 🆘 자주 쓰는 명령어

```bash
# 컨테이너 실행 (requirements.txt가 바뀌었으면 --build)
docker compose up --build

# 새 앱 만들기
docker compose exec web python manage.py startapp <앱이름>

# 마이그레이션
docker compose exec web python manage.py makemigrations
docker compose exec web python manage.py migrate

# 관리자 계정
docker compose exec web python manage.py createsuperuser

# 테스트 실행
docker compose exec web python manage.py test

# 컨테이너 안 셸 접속
docker compose exec web bash

# 로그 보기
docker compose logs -f web

# DB까지 싹 초기화 (주의: 로컬 DB 데이터 전부 삭제)
docker compose down -v
```
