"""
판정 결과의 화면 표시 정책 — 문구·색·모양은 이 파일 한 곳에서만 관리한다 (기획 v2 3.1, 12장 2번).

- 빨간색 금지 (가게 낙인 방지). 색은 static/css/common.css 의 --judge-* 변수와 같은 이름을 쓴다.
- 색만으로 구분하지 않고 모양·아이콘을 같이 쓴다 (색약 대응).
- hidden_by_default: 지도에서 기본으로 숨김 ("모든 장소 보기"를 켜야 보임, 기획 v2 3.2)
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
        "label": "혼자 들어가기 어려워요",
        "css_var": "--judge-difficult",
        "shape": "circle",
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


def display(outcome):
    return {"code": outcome, **DISPLAY[Outcome(outcome)]}
