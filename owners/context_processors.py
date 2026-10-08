"""
모든 화면 상단 메뉴:
- '내 가게' 링크 (인증 신청이 있는 사장님·건물주에게만)
- '가고 싶어요' 링크 + 좋아진 가게 수 (가고 싶어요를 누른 적 있는 사람에게만, 기획 v2 6.2)
"""

from .services import improved_wish_count, owner_menu


def owner_nav(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}  # 로그인 안 한 사람은 DB 조회 없이 넘어감
    return {"owner_nav": owner_menu(user), "wish_nav": improved_wish_count(user)}
