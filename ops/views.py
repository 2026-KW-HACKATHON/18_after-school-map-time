"""
운영자 화면 (와이어프레임 10~18번). 관리자(is_staff)만 들어올 수 있다.
Django 관리자(/admin/)는 데이터 전체를 다루는 도구로 남겨 두고, 여기는 매일 하는 일(제보 검토·장소 등록)만 쉽게.
"""

from datetime import timedelta

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import views as auth_views
from django.db.models import Max, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone

from judgments.constants import display
from judgments.services import report_direction, report_effect
from places.models import Place, Region
from reports.models import Report

from . import services
from .templatetags.ops_tags import OPS_STATUS_LABELS
from .forms import ENTRANCE_KEYS, PLACE_KEYS, PlaceForm, ReviewForm

staff_required = staff_member_required(login_url=reverse_lazy("ops:login"))


def _region():
    """위치 선택 지도의 처음 중심"""
    return Region.objects.filter(is_active=True).order_by("id").first()


class OpsLoginView(auth_views.LoginView):
    """운영자 로그인 (10번). 관리자 계정의 아이디·비밀번호 (주민은 카카오 로그인)"""

    template_name = "ops/login.html"
    redirect_authenticated_user = True

    def get_success_url(self):
        return self.get_redirect_url() or reverse_lazy("ops:dashboard")


@staff_required
def dashboard(request):
    """운영자 대시보드 (11번)"""
    today = timezone.localdate()
    user_reports = Report.objects.filter(source=Report.Source.USER_REPORT)
    places = Place.objects.filter(is_closed=False)
    return render(request, "ops/dashboard.html", {
        "pending": user_reports.filter(status=Report.Status.PENDING).count(),
        "approved_today": user_reports.filter(status=Report.Status.VERIFIED, reviewed_at__date=today).count(),
        "rejected_today": user_reports.filter(status=Report.Status.REJECTED, reviewed_at__date=today).count(),
        "recent_reports": user_reports.select_related("place", "entrance__place", "building").order_by("-created_at")[:5],
        "public_places": places.count(),
        "new_places_week": places.filter(created_at__gte=timezone.now() - timedelta(days=7)).count(),
        "recent_places": places.order_by("-updated_at")[:5],
    })


STATUS_TABS = [("", "전체")] + list(OPS_STATUS_LABELS.items())


@staff_required
def report_list(request):
    """제보 검토 목록 (15번). 대기 중 제보에는 판정 하향·새 장소·새 계정 표시"""
    status = request.GET.get("status", "PENDING")
    reports = Report.objects.filter(source=Report.Source.USER_REPORT).select_related(
        "place", "entrance__place", "entrance__building", "building", "created_by"
    ).prefetch_related("values__field").order_by("-created_at")
    counts = {s: reports.filter(status=s).count() for s, _ in STATUS_TABS if s}
    if status:
        reports = reports.filter(status=status)
    rows = []
    for r in reports[:100]:
        pending = r.status == Report.Status.PENDING
        rows.append({
            "report": r,
            # 검토 판단에 쓰는 표시라 대기 중 제보에만
            "downgrade": pending and report_direction(r) == "DOWN",
            "new_account": pending and r.created_by is not None and r.created_by.is_new_account(),
        })
    return render(request, "ops/report_list.html", {
        "rows": rows, "status": status, "tabs": STATUS_TABS, "counts": counts,
    })


@staff_required
def report_review(request, pk):
    """제보 상세 검토 (16번) + 충돌 정보 확인 (17번). 승인·반려는 확인 창을 거친다"""
    report = get_object_or_404(Report.objects.select_related("created_by", "entrance__place"), pk=pk)
    form = ReviewForm(request.POST or None, report=report, initial={
        "place_name": report.suggested_name, "lat": report.lat, "lng": report.lng,
    })
    if request.method == "POST" and report.status == Report.Status.PENDING and form.is_valid():
        data = form.cleaned_data
        if data["action"] == "approve":
            services.approve_report(report, request.user, data["review_note"], new_place={
                "name": data["place_name"], "category": data["category"], "lat": data["lat"], "lng": data["lng"],
            })
        else:
            services.reject(report, request.user, data["reject_reason"], data["review_note"])
        return redirect("ops:report-done", pk=report.pk)

    # 승인하면 판정이 어떻게 바뀌는지 (판정 엔진에 제보 값을 가상으로 넣어 계산)
    effect = report_effect(report) if report.status == Report.Status.PENDING else []
    changes = [
        {"profile": c.profile.label, "before_label": display(c.before)["label"],
         "after_label": display(c.after)["label"], "direction": c.direction}
        for c in effect if c.before != c.after
    ]
    return render(request, "ops/report_review.html", {
        "report": report,
        "form": form,
        "diff": services.report_diff(report),
        "changes": changes,
        "direction": report_direction(report, effect) if effect else None,
        "downgrade_places": services.recent_downgrade_places(report.created_by),
        "abuse_threshold": services.ABUSE_PLACE_COUNT,
        "confirmations": report.confirmations.select_related("user"),
        "region": _region(),
    })


@staff_required
def report_done(request, pk):
    """제보 처리 완료 (18번)"""
    return render(request, "ops/report_done.html", {"report": get_object_or_404(Report, pk=pk)})


@staff_required
def place_list(request):
    q = request.GET.get("q", "").strip()
    places = Place.objects.order_by("-updated_at")
    if q:
        places = places.filter(Q(name__icontains=q) | Q(address__icontains=q))
    return render(request, "ops/place_list.html", {"places": places[:100], "q": q})


@staff_required
def place_edit(request, pk=None):
    """장소 등록·수정 (12번). 필수 항목이 비면 누락 안내(13번), 저장하면 완료 안내(14번)"""
    place = get_object_or_404(Place, pk=pk) if pk else None
    form = PlaceForm(request.POST or None, instance=place, door_choices=services.door_type_choices())
    if request.method == "POST" and form.is_valid():
        saved = services.save_place_survey(form, request.user)
        return redirect("ops:place-saved", pk=saved.pk)
    return render(request, "ops/place_form.html", {
        "form": form,
        "place": place,
        "entrance_fields": [form[k] for k in ENTRANCE_KEYS],
        "place_fields": [form[k] for k in PLACE_KEYS],
        "missing": form.missing_required() if form.is_bound else [],
        "region": _region(),
    })


@staff_required
def place_saved(request, pk):
    """장소 저장 완료 (14번)"""
    place = get_object_or_404(Place, pk=pk)
    last = place.reports.aggregate(last=Max("observed_at"))["last"]
    return render(request, "ops/place_saved.html", {"place": place, "last": last})
