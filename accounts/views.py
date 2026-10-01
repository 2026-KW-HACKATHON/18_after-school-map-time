from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .activity import activity


@login_required
def me(request):
    """내 활동: 내 제보 현황(확인 중·반영·반려 사유), 기여 수, 배지"""
    return render(request, "accounts/me.html", activity(request.user))
