from datetime import datetime, time

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.template.loader import render_to_string
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.validation import parse_pk
from judgments.services import required_confirmations
from places.facilities import ENTRANCE, KIND_FIELDS
from places.models import Building, Entrance, Place, Region

from . import ai
from .forms import PhotoFixForm, ReportForm
from .models import PHOTO_FIX_PREFIX, AccessibilityValue, Report
from .services import ConfirmationError, confirm_report, reconfirm_place


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
    place_id = request.GET.get("place") or request.POST.get("place")
    if place_id:
        place_id = parse_pk(place_id)
        if place_id is None:
            raise Http404("장소를 찾을 수 없어요.")
        place = get_object_or_404(Place, pk=place_id, is_closed=False)

    building = None
    building_id = request.GET.get("building") or request.POST.get("building")
    if building_id:
        building_id = parse_pk(building_id)
        if building_id is None or place is not None:
            raise Http404("건물을 찾을 수 없어요.")
        building = get_object_or_404(Building, pk=building_id, region__is_active=True)
    kind = request.GET.get("facility_kind") or ENTRANCE
    ownership = request.GET.get("ownership") or ("BUILDING" if building else "PLACE")
    form = ReportForm(request.POST or None, request.FILES or None, place=place, building=building,
                      user=request.user, kind=kind, ownership=ownership)
    reference = request.GET.get("target_reference")
    if reference in form.targets:
        form.initial["target_reference"] = reference
    show_picker = ((place is None and building is None) or form.kind != ENTRANCE or
                   form.ownership == "BUILDING" or "facility_kind" in request.GET)
    kind_label = dict(form.fields["facility_kind"].choices)[form.kind]
    region = (place.region if place else building.region if building else
              Region.objects.filter(is_active=True).order_by("id").first())
    if request.method == "GET" and request.GET.get("partial") == "facility-fields":
        # 화면 전환도 실제 제출과 같은 Form으로 만들어 항목·시설 소속 검증을 일치시킨다.
        if kind not in KIND_FIELDS or ownership not in dict(form.fields["ownership"].choices):
            return JsonResponse({"error": "시설 종류와 소속을 확인해 주세요."}, status=400)
        return JsonResponse({
            "kind": form.kind, "ownership": form.ownership, "label": kind_label,
            "fields_html": render_to_string("reports/_observation_fields.html", {"form": form}, request=request),
            "targets": list(form.fields["target_reference"].choices),
            "target": form.initial["target_reference"],
            "photo_label": form.fields["photo"].label,
            "photo_help": form.fields["photo"].help_text,
            "show_picker": show_picker,
            "location_html": render_to_string("reports/_location_fields.html", {
                "form": form, "region": region, "kind_label": kind_label,
            }, request=request),
        })
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
                location_text=data.get("location_text", ""),
                ai_notice_version=form.notice_version,  # 이 폼에 붙어 있던 AI 안내 버전 (없으면 빈 값)
            )
            observed_on = data.get("observed_on")
            if observed_on and observed_on < timezone.localdate():
                report.observed_at = timezone.make_aware(datetime.combine(observed_on, time(12)))
            reference = data.get("target_reference") or form.initial["target_reference"]
            target = form.targets.get(reference)
            if target is not None:
                if form.kind == ENTRANCE:
                    report.entrance = target
                else:
                    report.facility = target
            elif reference == "default" and place is not None:
                report.entrance = _main_entrance(place)
            else:
                # 명시적 새 시설 제안은 승인 전 기존 출입구/시설을 만들거나 바꾸지 않는다.
                if form.parent is not None:
                    setattr(report, "building" if form.ownership == "BUILDING" else "place", form.parent)
                else:
                    report.suggested_name = data["suggested_name"]
                    for key in ("suggested_category", "suggested_address", "suggested_floor", "suggested_phone"):
                        setattr(report, key, data[key])
                if form.parent is not None or form.kind != ENTRANCE or data.get("facility_name"):
                    report.facility_kind = form.kind
                report.facility_name = data.get("facility_name", "")
            report.save()
            for key, raw in form.observation_values().items():
                value = AccessibilityValue(report=report, field_id=key)
                value.set_value(raw)
                value.full_clean()
                value.save()
        return redirect("reports:done")

    if request.method == "POST":
        form.keep_photo_for_retry()  # 오류가 있으면 올린 사진을 보관해서 다시 고르지 않게
    return render(request, "reports/report_form.html", {
        "form": form, "place": place, "building": building, "region": region,
        "selected_ownership": form.ownership,
        "show_picker": show_picker, "kind_label": kind_label,
        # AI 검토 보조를 켜면 사진·설명이 OpenAI로 갈 수 있음을 안내 (AI_NOTICE_SINCE를 이 문구를 붙인 시각으로)
        "ai_notice": ai.NOTICE_TEXT if ai.notice_active() else "",
    })


def report_done(request):
    return render(request, "reports/report_done.html")


def _safe_next(request):
    back = request.POST.get("next") or "/"
    if not url_has_allowed_host_and_scheme(back, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        back = "/"
    return back


@login_required
def photo_fix_request(request, pk):
    """
    입구 사진 수정 요청 (주민 → 운영자, 기획 v2 4.4): 예전 모습이거나 얼굴·번호판이 보일 때.
    운영자가 새 사진으로 바꾸거나 지금 사진을 내린다. 같은 입구에 내 요청이 확인 중이면 다시 못 냄
    """
    entrance = get_object_or_404(Entrance.objects.select_related("place", "building"), pk=pk)
    place = entrance.place or (entrance.building.places.filter(is_closed=False).first() if entrance.building else None)
    if place is None or place.is_closed:
        raise Http404("장소를 찾을 수 없어요.")
    back = request.GET.get("next") or request.POST.get("next") or ""
    if not back or not url_has_allowed_host_and_scheme(back, allowed_hosts={request.get_host()},
                                                        require_https=request.is_secure()):
        back = reverse("places:detail", args=[place.pk])

    form = PhotoFixForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        busy = Report.objects.filter(entrance=entrance, created_by=request.user, status=Report.Status.PENDING,
                                     note__startswith=PHOTO_FIX_PREFIX).exists()
        if busy:
            form.add_error(None, "이 입구 사진에 보낸 요청이 아직 확인 중이에요.")
        else:
            data = form.cleaned_data
            Report.objects.create(
                source=Report.Source.USER_REPORT, status=Report.Status.PENDING, created_by=request.user,
                entrance=entrance, photo=data["photo"] or "",
                note=" · ".join(filter(None, [f"{PHOTO_FIX_PREFIX} {data['reason']}", data["note"]]))[:500],
            )
            messages.success(request, "사진 수정 요청을 보냈어요. 운영진이 확인하면 알림으로 알려 드려요.")
            return redirect(back)
    if request.method == "POST":
        form.keep_photo_for_retry()
    return render(request, "reports/photo_fix_form.html", {"form": form, "entrance": entrance, "place": place,
                                                          "next": back})


@login_required
@require_POST
def place_reconfirm(request, pk):
    """"지금도 맞아요" — 판정은 그대로, 최근 확인일만 갱신"""
    place = get_object_or_404(Place, pk=pk, is_closed=False)
    try:
        reconfirm_place(place, request.user)
    except ConfirmationError as e:
        messages.error(request, str(e))
    else:
        messages.success(request, "확인해 주셔서 고마워요. 최근 확인일이 오늘로 바뀌었어요.")
    return redirect(_safe_next(request))


@login_required
@require_POST
def report_confirm(request, pk):
    """다른 주민의 '맞아요' 확인 (장소 상세의 확인 중인 제보)"""
    report = get_object_or_404(Report, pk=pk)
    back = request.POST.get("next") or "/"
    # 되돌아갈 주소는 우리 사이트 안만 허용 (//다른사이트.com 같은 외부 이동 방지)
    if not url_has_allowed_host_and_scheme(back, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        back = "/"
    required = required_confirmations(report)
    if required is None:  # 사진 교체 요청·새 계정의 하향 제보처럼 운영자만 처리하는 제보
        messages.error(request, "이 제보는 운영진이 확인해요.")
        return redirect(back)
    try:
        applied = confirm_report(report, request.user, required)
    except ConfirmationError as e:
        messages.error(request, str(e))
    else:
        messages.success(request, "확인해 주셔서 고마워요. 지도에 반영됐어요." if applied
                         else "확인해 주셔서 고마워요. 다른 주민의 확인이 더 모이면 반영돼요.")
    return redirect(back)
