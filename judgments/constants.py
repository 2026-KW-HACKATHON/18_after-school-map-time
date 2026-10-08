"""
판정 결과의 화면 표시 정책 — 문구·색·모양은 이 파일 한 곳에서만 관리한다 (기획 v2 3.1, 12장 2번).

- 빨간색 금지 (가게 낙인 방지). 색은 static/css/common.css 의 --judge-* 변수와 같은 이름을 쓴다.
- 색만으로 구분하지 않고 모양·아이콘을 같이 쓴다 (색약 대응).
- hidden_by_default: API 기본 필터/지도 "모든 장소 보기" OFF에서 숨기는 항목.
  · 지도 토글은 기본 ON(전체 표시), OFF이면 가능·조건부만 표시한다.
  · 어려움은 공개 화면에서 정보 없음으로 통합한다. 내부 판정·확인된 사실은 보존한다 (2026-10-09).
"""

from .models import Outcome

DISPLAY = {
    Outcome.ACCESSIBLE: {
        "label": "들어갈 수 있어요",
        "css_var": "--judge-accessible",
        "shape": "circle",
        "icon": "",
        "hidden_by_default": False,
    },
    Outcome.CONDITIONAL: {
        "label": "도움 받으면 들어갈 수 있어요",
        "css_var": "--judge-conditional",
        "shape": "circle",
        "icon": "hand",
        "hidden_by_default": False,
    },
    Outcome.DIFFICULT: {
        "label": "아직 정보가 없어요 · 알려주세요",
        "css_var": "--judge-unknown",
        "shape": "dashed-circle",
        "icon": "",
        "hidden_by_default": True,
    },
    Outcome.UNKNOWN: {
        "label": "아직 정보가 없어요 · 알려주세요",
        "css_var": "--judge-unknown",
        "shape": "dashed-circle",
        "icon": "",
        "hidden_by_default": True,
    },
}

# 장소의 여러 출입구(경로) 중 "가장 좋은 것"을 고를 때의 순서.
# 알 수 없는 경로가 있으면 어려움으로 단정하지 않는다 (가게 부담 최소화, OP-1·OP-2)
BEST_ROUTE_ORDER = [Outcome.ACCESSIBLE, Outcome.CONDITIONAL, Outcome.UNKNOWN, Outcome.DIFFICULT]

# "개선 완료" 배지 판단용 순위 (미확인은 개선 비교에서 제외)
IMPROVEMENT_RANK = {Outcome.DIFFICULT: 1, Outcome.CONDITIONAL: 2, Outcome.ACCESSIBLE: 3}


def display(outcome, *, internal=False):
    # 기존 API code 및 owners의 수요 신호는 유지하고 공개 표시 분류만 통합한다.
    payload = {"code": outcome, "display_code": Outcome.UNKNOWN if outcome == Outcome.DIFFICULT else outcome,
               **DISPLAY[Outcome(outcome)]}
    if internal and outcome == Outcome.DIFFICULT:
        # 운영자 검토에서는 판정 변화와 원본 의미를 정확히 구분해야 한다.
        payload.update(label="혼자 들어가기 어려워요", css_var="--judge-difficult", shape="circle", display_code=outcome)
    return payload
