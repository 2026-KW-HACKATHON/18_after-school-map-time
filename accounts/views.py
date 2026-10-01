from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from .activity import activity
from .models import Notification


@login_required
def me(request):
    """내 활동: 내 제보 현황(확인 중·반영·반려 사유), 기여 수, 배지"""
    return render(request, "accounts/me.html", activity(request.user))


@login_required
def notifications(request):
    """알림 목록 (최근 50개). 이 화면을 열면 안 읽은 알림은 읽음으로 바뀐다 — 새 알림은 '새' 표시로 한 번 보여 줌"""
    items = list(Notification.objects.filter(user=request.user)[:50])
    unread_ids = {n.pk for n in items if not n.is_read}
    Notification.objects.filter(user=request.user, read_at__isnull=True).update(read_at=timezone.now())
    return render(request, "accounts/notifications.html", {
        "items": [{"n": n, "new": n.pk in unread_ids} for n in items],
        "notif_unread": 0,  # 방금 읽음 처리했으니 메뉴 숫자도 0으로
    })
