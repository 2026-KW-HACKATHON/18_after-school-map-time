"""
운영자 화면 (와이어프레임 10~18번). 관리자(is_staff)만 들어올 수 있다.
Django 관리자(/admin/)는 데이터 전체를 다루는 도구로 남겨 두고, 여기는 매일 하는 일(제보 검토·장소 등록)만 쉽게.
"""

from datetime import timedelta

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import views as auth_views
from django.db.models import Max, Q
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.urls import reverse_lazy
from django.utils import timezone

from judgments.constants import display
from judgments.services import is_owner_declaration, report_direction, report_effect, required_confirmations
from owners.models import ClaimCode, OwnerClaim
from owners.services import CORRECTION_OVERDUE_DAYS
from places.models import Place, Region
from reports.models import Report

from . import services
from .templatetags.ops_tags import OPS_STATUS_LABELS
from .forms import ENTRANCE_KEYS, PLACE_KEYS, PlaceForm, ReviewForm

staff_required = staff_member_required(login_url=reverse_lazy("ops:login"))

# 운영자가 검토하는 제보: 주민 제보 + 사장님 요청(선언·정정)
REVIEW_SOURCES = [Report.Source.USER_REPORT, Report.Source.OWNER]


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
    review_reports = Report.objects.filter(source__in=REVIEW_SOURCES)
    places = Place.objects.filter(is_closed=False)
    return render(request, "ops/dashboard.html", {
        "pending_claims": OwnerClaim.objects.filter(status=OwnerClaim.Status.PENDING).count(),
        # 기획 v2 4.3: 사장님 정정 요청이 7일 넘게 처리 안 되면 알림
        "overdue_owner": review_reports.filter(
            source=Report.Source.OWNER, status=Report.Status.PENDING,
            created_at__lt=timezone.now() - timedelta(days=CORRECTION_OVERDUE_DAYS),
        ).count(),
        "pending": review_reports.filter(status=Report.Status.PENDING).count(),
        "approved_today": review_reports.filter(status=Report.Status.VERIFIED, reviewed_at__date=today).count(),
        "rejected_today": review_reports.filter(status=Report.Status.REJECTED, reviewed_at__date=today).count(),
        "recent_reports": review_reports.select_related("place", "entrance__place", "building").order_by("-created_at")[:5],
        "public_places": places.count(),
        "new_places_week": places.filter(created_at__gte=timezone.now() - timedelta(days=7)).count(),
        "recent_places": places.order_by("-updated_at")[:5],
    })


STATUS_TABS = [("", "전체")] + list(OPS_STATUS_LABELS.items())


def _owner_kind(report):
    """사장님 요청 종류 표시 (선언은 확인 1명, 정정은 2명 — 기획 v2 4.2·4.3)"""
    if report.source != Report.Source.OWNER:
        return ""
    return "사장님 선언" if is_owner_declaration(report) else "사장님 정정 요청"


@staff_required
def report_list(request):
    """제보 검토 목록 (15번). 대기 중 제보에는 판정 하향·새 장소·새 계정 표시"""
    status = request.GET.get("status", "PENDING")
    reports = Report.objects.filter(source__in=REVIEW_SOURCES).select_related(
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
            "owner_kind": _owner_kind(r),
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
        "category": report.suggested_category,
        "address": report.suggested_address or report.location_text,
        "floor": report.suggested_floor, "phone": report.suggested_phone,
    })
    if request.method == "POST" and report.status == Report.Status.PENDING and form.is_valid():
        data = form.cleaned_data
        if data["action"] == "approve":
            services.approve_report(report, request.user, data["review_note"], new_place={
                "name": data["place_name"], "category": data["category"], "lat": data["lat"], "lng": data["lng"],
                # 이전 화면에서 보낸 요청도 제보의 주소를 잃지 않도록 한다.
                "address": data["address"] if "address" in request.POST else report.suggested_address or report.location_text,
                "floor": data["floor"], "phone": data["phone"],
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
        "required": required_confirmations(report),
        "owner_kind": _owner_kind(report),
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
    form = PlaceForm(request.POST or None, instance=place, door_choices=services.door_type_choices(),
                     initial=services.entrance_form_initial(place) if place else {})
    if request.method == "POST" and form.is_valid():
        saved = services.save_place_survey(form, request.user)
        return redirect("ops:place-saved", pk=saved.pk)
    return render(request, "ops/place_form.html", {
        "form": form,
        "place": place,
        "claim_codes": place.claim_codes.order_by("-created_at")[:5] if place else [],
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


@staff_required
def claim_list(request):
    """사장님·건물주 인증 신청 (기획 v2 4.1). 코드가 맞는 가게인지 확인하고 승인"""
    if request.method == "POST":
        claim = get_object_or_404(OwnerClaim, pk=request.POST.get("claim"), status=OwnerClaim.Status.PENDING)
        if request.POST.get("action") == "approve":
            claim.review(OwnerClaim.Status.APPROVED, request.user)
            messages.success(request, f"{claim.user}님을 {claim.place or claim.building} 사장님으로 승인했어요.")
        else:
            claim.review(OwnerClaim.Status.REJECTED, request.user, request.POST.get("reason", "")[:200])
            messages.success(request, "반려했어요.")
        return redirect("ops:claims")
    claims = OwnerClaim.objects.select_related("user", "place", "building", "code").order_by("status", "-created_at")
    return render(request, "ops/claim_list.html", {"claims": claims[:100]})


@staff_required
@require_POST
def issue_claim_code(request, pk):
    """장소 인증 코드 발급 — 답사 때 가게에 전달 (1회용)"""
    place = get_object_or_404(Place, pk=pk)
    code = ClaimCode.issue(place=place)
    messages.success(request, f"인증 코드 {code.code} 를 발급했어요. 사장님께 전달해 주세요.")
    return redirect("ops:place-edit", pk=place.pk)
