"""상단 메뉴 '알림' 의 안 읽은 개수 (로그인한 사람만, 쿼리 한 번)"""

from .models import Notification


def notifications(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}
    return {"notif_unread": Notification.objects.filter(user=user, read_at__isnull=True).count()}
