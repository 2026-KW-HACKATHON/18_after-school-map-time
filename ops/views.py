"""
운영자 화면 (와이어프레임 10~18번). 관리자(is_staff)만 들어올 수 있다.
Django 관리자(/admin/)는 데이터 전체를 다루는 도구로 남겨 두고, 여기는 매일 하는 일(제보 검토·장소 등록)만 쉽게.
"""

import csv
import uuid
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import views as auth_views
from django.db.models import Max, Q
from django.contrib import messages
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST, require_http_methods
from django.urls import reverse, reverse_lazy
from django.utils import timezone

from core.validation import parse_pk
from judgments.constants import display
from judgments.models import Outcome
from judgments.services import is_owner_declaration, is_photo_request, report_direction, report_effect, required_confirmations
from owners.models import ClaimCode, OwnerClaim
from owners.services import CORRECTION_OVERDUE_DAYS
from places.models import Building, FieldDefinition, Place, Region
from reports import ai
from reports.models import AIAnalysis, Report
from reports.selectors import latest_photo

from . import district as district_data
from . import services
from .templatetags.ops_tags import OPS_STATUS_LABELS
from .forms import (ENTRANCE_KEYS, PLACE_KEYS, AIAnalyzeForm, AISelectionForm, PlaceDeleteForm, PlaceForm,
                    ReportDeleteForm, ReviewForm)

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
        # AI 검토 보조: 켰을 때만 오늘 사용량과 설정 경고
        "ai_enabled": settings.AI_ENABLED, "ai_warnings": ai.config_warnings(),
        "ai_attempts": ai.attempts_today(), "ai_limit": settings.AI_DAILY_LIMIT,
    })


STATUS_TABS = [("", "전체")] + list(OPS_STATUS_LABELS.items())


def _owner_kind(report):
    """
    요청 종류 표시 — 사장님 선언은 확인 1명, 정정은 2명, 사진 교체·수정은 운영자만 (기획 v2 4.2~4.4).
    주민의 사진 수정 요청도 여기서 구분한다. 일반 주민 제보는 빈 문자열
    """
    if report.source == Report.Source.USER_REPORT:
        return "주민 사진 수정 요청" if is_photo_request(report) else ""
    if report.source != Report.Source.OWNER:
        return ""
    if is_photo_request(report):
        return "사장님 사진 교체 요청"
    if report.target_place is None:  # 건물·건물 출입구 대상
        return "건물주 정정 요청"
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
    action = request.POST.get("action") if request.method == "POST" else None
    if action == "ai_analyze":
        return _ai_analyze(request, report)
    selection_form = None
    if action == "ai_save":
        selection_form, response = _ai_save(request, report)
        if response is not None:
            return response
    # AI 폼을 다시 보여 줄 때는 승인·반려 폼을 검증하지 않는다 (action별로 해당 폼만)
    form = ReviewForm(request.POST if request.method == "POST" and action != "ai_save" else None, report=report, initial={
        "place_name": report.suggested_name, "lat": report.lat, "lng": report.lng,
        "category": report.suggested_category,
        "address": report.suggested_address or report.location_text,
        "floor": report.suggested_floor, "phone": report.suggested_phone,
    })
    if form.is_bound and report.status == Report.Status.PENDING and form.is_valid():
        data = form.cleaned_data
        if data["action"] == "approve":
            if data.get("remove_current_photo") and is_photo_request(report) and report.entrance_id:
                services.remove_current_photo(report.entrance, keep=report)
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
        "confirmations": ai.effective_confirmations(report),  # AI 후보를 저장한 제보는 0건
        "required": required_confirmations(report),
        "owner_kind": _owner_kind(report),
        # 사진 교체·수정 요청이면 지금 공개된 사진과 나란히 보여 줌
        "photo_request": is_photo_request(report),
        "current_photo": latest_photo(report.entrance) if report.entrance_id else None,
        "region": _region(),
        "ai": _ai_panel(report, selection_form),
    })


def _ai_back(report):
    return reverse("ops:report-review", args=[report.pk]) + "#ai"


def _ai_analyze(request, report):
    """'AI 후보 불러오기' → 분석하거나 같은 입력의 이전 결과를 다시 씀. 실패해도 제보·판정은 그대로"""
    if not AIAnalyzeForm(request.POST).is_valid():
        messages.error(request, "보내기 전에 개인정보 확인에 체크해 주세요.")
        return redirect(_ai_back(report))
    try:
        _, reused = ai.analyze(report, request.user)
    except ai.AIError as e:
        messages.error(request, e.message)
    else:
        messages.success(request, "이전에 분석한 결과를 다시 보여 드려요." if reused
                         else "AI 후보를 불러왔어요. 근거를 보고 맞는 항목만 골라 저장해 주세요.")
    return redirect(_ai_back(report))


def _ai_save(request, report):
    """고른 후보 저장 → (다시 보여 줄 폼, 응답). 칸 오류면 폼을 돌려주고 같은 화면에 오류 표시"""
    try:
        analysis = report.ai_analyses.get(pk=uuid.UUID(request.POST.get("analysis_id", "")))
    except (ValueError, AIAnalysis.DoesNotExist):
        raise Http404("분석 기록을 찾을 수 없어요.")
    form = AISelectionForm(request.POST, analysis=analysis, definitions=ai.active_definitions(report),
                           report_values=_report_values(report), labels=_field_labels(report),
                           all_keys=ai.analysis_keys(report))
    if not form.is_valid():
        return form, None
    try:
        changes = ai.save_selection(analysis, request.user, form.selections())
    except ai.AIError as e:
        messages.error(request, e.message)
    else:
        messages.success(request, f"{len(changes)}개 항목을 제보에 저장했어요. 이 제보는 이제 운영자만 승인할 수 있어요.")
    return None, redirect(_ai_back(report))


def _field_labels(report):
    return dict(FieldDefinition.objects.filter(key__in=ai.analysis_keys(report)).values_list("key", "label"))


def _report_values(report):
    return {v.field_id: v for v in report.values.select_related("field")}


def _shown(value):
    return ("있음" if value else "없음") if isinstance(value, bool) else ("-" if value is None else value)


def _ai_panel(report, selection_form=None):
    """운영자 검토 화면의 AI 영역: 보낼 내용 미리보기, 최근 분석 결과, 후보 선택 폼, 선택 기록"""
    analyses = list(report.ai_analyses.select_related("requested_by"))
    staff_only = any(a.selection_history for a in analyses)
    blocked = ai.config_error() or ai.unsupported_reason(report)
    blocked_message = ai.notice_reason(report) if blocked == "NOTICE_NOT_APPLIED" else ai.MESSAGES.get(blocked, "")
    labels = _field_labels(report)
    panel = {
        "enabled": settings.AI_ENABLED, "blocked": blocked_message, "warnings": ai.config_warnings(),
        "masked_note": ai.mask_phone(report.note), "analyze_form": AIAnalyzeForm(), "recipient": ai.recipient(),
        "attempts": ai.attempts_today(), "limit": settings.AI_DAILY_LIMIT,
        "staff_only": staff_only, "excluded_confirmations": report.confirmations.count() if staff_only else 0,
        "history": [
            {**entry, "at": datetime.fromisoformat(entry["at"]),
             "changes": [{"label": labels.get(c["key"], c["key"]), "before": _shown(c["before"]),
                                   "after": _shown(c["after"])} for c in entry["changes"]]}
            for a in analyses for entry in a.selection_history
        ],
        "latest": analyses[0] if analyses else None,
    }
    latest = panel["latest"]
    if latest is None:
        return panel
    panel["status"] = ai.effective_status(latest)
    panel["error_code"], panel["error_message"] = ai.effective_error(latest)
    if panel["status"] != AIAnalysis.Status.SUCCEEDED:
        return panel
    if latest.schema_version != ai.schema_version_for(report):  # 이전 버전 결과는 바꿔 쓰지 않음
        panel["old_schema"] = True
        return panel
    result = latest.result
    panel["summary"] = result["summary"]
    panel["warnings"] = [ai.WARNINGS[w] for w in result["warnings"]]
    panel["manual_check_items"] = result["manual_check_items"]
    if latest.selection_history or report.status != Report.Status.PENDING:
        return panel
    if ai.input_changed(latest):
        panel["input_changed"] = True
        return panel
    panel["selection_form"] = selection_form or AISelectionForm(
        analysis=latest, definitions=ai.active_definitions(report), report_values=_report_values(report),
        labels=labels, all_keys=ai.analysis_keys(report))
    return panel


@staff_required
@require_POST
def reports_delete(request):
    """
    제보 기록 삭제: 목록에서 고른 기록(또는 상세의 한 건) → 확인 화면 → 동의하면 삭제.
    주민 제보·사장님 요청만 (팀 답사·공공데이터 기록은 여기서 지우지 않음)
    """
    ids = [pk for raw in request.POST.getlist("ids") if (pk := parse_pk(raw)) is not None]
    back = request.POST.get("back", "")
    back_url = reverse("ops:reports") + (f"?status={back}" if back in OPS_STATUS_LABELS or back == "" else "")
    reports = list(Report.objects.filter(pk__in=ids, source__in=REVIEW_SOURCES)
                   .select_related("place", "entrance__place", "entrance__building", "building", "created_by")
                   .order_by("-created_at"))
    if not reports:
        messages.error(request, "지울 기록을 하나 이상 골라 주세요.")
        return redirect(back_url)
    form = ReportDeleteForm(request.POST if "confirm_step" in request.POST else None)
    if form.is_bound and form.is_valid():
        count = services.delete_reports(reports)
        messages.success(request, f"제보 기록 {count}건을 삭제했어요.")
        return redirect(back_url)
    return render(request, "ops/report_delete.html", {
        "form": form, "reports": reports, "back": back,
        "verified": sum(1 for r in reports if r.status == Report.Status.VERIFIED),
        "photos": sum(1 for r in reports if r.photo),
    })


@staff_required
def report_done(request, pk):
    """제보 처리 완료 (18번)"""
    return render(request, "ops/report_done.html", {"report": get_object_or_404(Report, pk=pk)})


@staff_required
def place_list(request):
    q = request.GET.get("q", "").replace("\x00", "").strip()  # NUL 문자는 PostgreSQL이 거부 → 500 방지
    places = Place.objects.select_related("building").prefetch_related(
        "entrances", "facilities", "building__entrances", "building__facilities").order_by("-updated_at")
    if q:
        places = places.filter(Q(name__icontains=q) | Q(address__icontains=q))
    places = list(places[:100])
    for place in places:
        place.facility_sections = services.facility_inventory(place)
    return render(request, "ops/place_list.html", {"places": places, "q": q})


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
        "building_claim_codes": place.building.claim_codes.order_by("-created_at")[:5]
        if place and place.building_id else [],
        "entrance_fields": [form[k] for k in ENTRANCE_KEYS],
        "place_fields": [form[k] for k in PLACE_KEYS],
        "missing": form.missing_required() if form.is_bound else [],
        "region": _region(),
        "facility_sections": services.facility_inventory(place, include_reports=True) if place else [],
    })


@staff_required
@require_http_methods(["GET", "POST"])
def place_delete(request, pk):
    """관리자만 확인 화면을 거쳐 삭제한다. GET 요청은 데이터를 변경하지 않는다."""
    place = get_object_or_404(Place, pk=pk)
    form = PlaceDeleteForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        name = place.name
        services.delete_place(place)
        messages.success(request, f"{name} 장소를 삭제했어요.")
        return redirect("ops:places")
    return render(request, "ops/place_delete.html", {"place": place, "form": form})


@staff_required
def place_saved(request, pk):
    """장소 저장 완료 (14번)"""
    place = get_object_or_404(Place, pk=pk)
    last = place.reports.aggregate(last=Max("observed_at"))["last"]
    return render(request, "ops/place_saved.html", {"place": place, "last": last})


def pending_counts():
    """검토를 기다리는 일: 제보·사장님 요청, 사장님·건물주 인증 신청"""
    return {
        "pending": Report.objects.filter(source__in=REVIEW_SOURCES, status=Report.Status.PENDING).count(),
        "claims": OwnerClaim.objects.filter(status=OwnerClaim.Status.PENDING).count(),
    }


@staff_required
def pending_status(request):
    """운영자 화면이 10초마다 묻는 검토 대기 수 (ops/static/ops/js/pending-poll.js)"""
    response = JsonResponse(pending_counts())
    response["Cache-Control"] = "no-store"
    return response


@staff_required
def poster(request):
    """
    전시·주민투표용 QR 포스터 (인쇄용 A4). 주민이 폰으로 찍으면 지도로 바로 들어온다.
    """
    return render(request, "ops/poster.html", {
        "site_url": request.build_absolute_uri(reverse("places:map")),
        "region": _region(),
        # 지도 표시 설명: 문구·색은 판정 표시 상수 한 곳에서 (기획 v2 3.1). 미확인은 포스터에서 생략
        "legend": [display(o) for o in (Outcome.ACCESSIBLE, Outcome.CONDITIONAL, Outcome.DIFFICULT)],
    })


@staff_required
def district(request):
    """구청용 지역 집계 (기획 v2 8장). 운영자만 — 공개 랭킹이 아니라 지원사업 대상 발굴용"""
    region = _region()
    return render(request, "ops/district.html", {
        "region": region,
        "summary": district_data.summary(region),
        "distribution": district_data.outcome_distribution(region),
        "candidates": district_data.support_candidates(region),
        "recheck": district_data.recheck_targets(region),
    })


@staff_required
def district_csv(request):
    """지원사업 검토 목록 CSV (구청 전달용, 엑셀에서 한글이 깨지지 않게 BOM)"""
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="support-candidates-{timezone.localdate():%Y%m%d}.csv"'
    response.write("\ufeff")
    writer = csv.writer(response)
    writer.writerow(district_data.CSV_HEADER)
    writer.writerows(district_data.candidate_csv_rows(district_data.support_candidates(_region())))
    return response


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


@staff_required
@require_POST
def issue_building_claim_code(request, pk):
    """건물주 인증 코드 발급 (기획 v2 5.2). 장소 수정 화면의 건물 칸에서 누른다"""
    building = get_object_or_404(Building, pk=pk)
    code = ClaimCode.issue(building=building)
    messages.success(request, f"건물주 인증 코드 {code.code} 를 발급했어요. 건물주님께 전달해 주세요.")
    place_id = parse_pk(request.POST.get("place", ""))
    place = building.places.filter(pk=place_id).first() if place_id is not None else None
    return redirect("ops:place-edit", pk=place.pk) if place else redirect("ops:places")


@staff_required
def claim_code_print(request, pk):
    """
    인증 코드 안내 쪽지 (인쇄용). 답사 때 가게에 두고 오면 사장님이 QR이나 주소로 바로 들어와
    코드가 채워진 화면에서 로그인만 하면 된다.
    """
    code = get_object_or_404(ClaimCode.objects.select_related("place", "building"), pk=pk)
    claim_url = request.build_absolute_uri(reverse("owners:claim")) + f"?code={code.code}"
    return render(request, "ops/claim_code_print.html", {"code": code, "claim_url": claim_url})
