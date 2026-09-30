"""모든 화면 상단 메뉴에 '내 가게' 링크 (인증 신청이 있는 사장님·건물주에게만)"""

from .services import owner_menu


def owner_nav(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}  # 로그인 안 한 사람은 DB 조회 없이 넘어감
    return {"owner_nav": owner_menu(user)}
