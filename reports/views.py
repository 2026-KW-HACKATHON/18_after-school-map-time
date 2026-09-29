from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from judgments.services import required_confirmations
from places.models import Entrance, Place

from .forms import ReportForm
from .models import AccessibilityValue, Report
from .services import ConfirmationError, confirm_report


def _main_entrance(place):
    """제보를 붙일 출입구: 주 출입구 → 아무 출입구 → 없으면 '정문'을 만든다"""
    entrance = place.entrances.filter(is_main=True).first() or place.entrances.first()
    return entrance or Entrance.objects.create(place=place, name="정문", is_main=True)


@login_required
def report_new(request):
    """
    제보 작성 (와이어프레임 8번). ?place=<id> 면 그 장소의 입구 제보, 없으면 새 장소 제안.
    모든 주민 제보는 '확인 중'으로 들어가고, 주민 확인 또는 운영자 승인 후 지도에 반영된다 (기획 v2 7장).
    """
    place = None
    if request.GET.get("place") or request.POST.get("place"):
        place = get_object_or_404(Place, pk=request.GET.get("place") or request.POST.get("place"), is_closed=False)

    form = ReportForm(request.POST or None, request.FILES or None, place=place, user=request.user)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        with transaction.atomic():
            report = Report(
                source=Report.Source.USER_REPORT,
                status=Report.Status.PENDING,
                created_by=request.user,
                photo=data["photo"],
                note=data["note"],
                profiles=data["profiles"],
                lat=data.get("lat"),
                lng=data.get("lng"),
            )
            if place is not None:
                report.entrance = _main_entrance(place)
            else:
                report.suggested_name = data["suggested_name"]
                report.location_text = data["location_text"]
            report.save()
            for key, raw in form.entrance_values().items():
                value = AccessibilityValue(report=report, field_id=key)
                value.set_value(raw)
                value.full_clean()
                value.save()
        return redirect("reports:done")

    return render(request, "reports/report_form.html", {"form": form, "place": place})


def report_done(request):
    return render(request, "reports/report_done.html")


@login_required
@require_POST
def report_confirm(request, pk):
    """다른 주민의 '맞아요' 확인 (장소 상세의 확인 중인 제보)"""
    report = get_object_or_404(Report, pk=pk)
    back = request.POST.get("next") or "/"
    # 되돌아갈 주소는 우리 사이트 안만 허용 (//다른사이트.com 같은 외부 이동 방지)
    if not url_has_allowed_host_and_scheme(back, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        back = "/"
    try:
        applied = confirm_report(report, request.user, required_confirmations(report))
    except ConfirmationError as e:
        messages.error(request, str(e))
    else:
        messages.success(request, "확인해 주셔서 고마워요. 지도에 반영됐어요." if applied
                         else "확인해 주셔서 고마워요. 다른 주민의 확인이 더 모이면 반영돼요.")
    return redirect(back)
