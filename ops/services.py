"""운영자 작업. 화면(views)과 분리해서 테스트하기 쉽게 둔다."""

from datetime import datetime, time, timedelta

from django.db import transaction
from django.utils import timezone

from judgments.engine import recompute_place
from judgments.services import DOWN, report_direction
from places.models import Entrance, FieldDefinition, Place, Region
from reports.models import AccessibilityValue, Report
from reports.selectors import current_values
from reports.services import reject_report, verify_report

from .forms import ENTRANCE_KEYS, PLACE_KEYS

ABUSE_DAYS = 7          # 기획 v2 7장: 7일 안에
ABUSE_PLACE_COUNT = 5   # 서로 다른 장소 5곳 이상 하향 제보 → 관리자 주의


def main_entrance(place):
    entrance = place.entrances.filter(is_main=True).first() or place.entrances.first()
    return entrance or Entrance.objects.create(place=place, name="정문", is_main=True)


def observed_at_for(observed_on):
    """
    확인일(날짜) → 확인 시각. 비었거나 오늘이면 지금 시각 → 오늘 앞서 입력한 기록보다 확실히 최신이 됨.
    지난 날짜면 그날 정오 (예전 답사 기록을 나중에 입력하는 경우)
    """
    if observed_on is None or observed_on >= timezone.localdate():
        return timezone.now()
    return timezone.make_aware(datetime.combine(observed_on, time(12, 0)))


def _survey_report(user, observed_at, note, **target):
    return Report.objects.create(
        source=Report.Source.TEAM_SURVEY, status=Report.Status.VERIFIED, created_by=user,
        reviewed_by=user, reviewed_at=timezone.now(), observed_at=observed_at, note=note, **target,
    )


def _save_values(report, values):
    for key, raw in values.items():
        value = AccessibilityValue(report=report, field_id=key)
        value.set_value(raw)
        value.full_clean()
        value.save()


@transaction.atomic
def save_place_survey(form, user):
    """
    장소 등록·수정 (와이어프레임 12번). 운영자가 입력한 접근성 값은 '팀 답사' 제보로 바로 반영(VERIFIED)하고 재판정한다.
    값의 이력이 남도록 기존 값을 고치지 않고 새 제보를 추가한다.
    """
    place = form.save(commit=False)
    if not place.region_id:
        place.region = Region.objects.filter(is_active=True).order_by("id").first()
    place.save()

    data = form.cleaned_data
    observed_at = observed_at_for(data.get("observed_on"))
    note = " · ".join(filter(None, [f"출처: {data['source_note']}" if data.get("source_note") else "", data.get("memo")]))

    entrance_values = form.values_for(ENTRANCE_KEYS)
    if entrance_values:
        _save_values(_survey_report(user, observed_at, note, entrance=main_entrance(place)), entrance_values)
    place_values = form.values_for(PLACE_KEYS)
    if place_values:
        _save_values(_survey_report(user, observed_at, note, place=place), place_values)

    recompute_place(place)
    return place


@transaction.atomic
def approve_report(report, user, review_note="", new_place=None):
    """
    제보 승인 (16·17번). 새 장소 제안이면 장소와 정문을 만들고 제보를 그 정문에 붙인 뒤 승인한다.
    new_place: {"name", "category", "lat", "lng", "address", "floor", "phone"}
    """
    if report.is_new_place:
        place = Place.objects.create(
            region=Region.objects.filter(is_active=True).order_by("id").first(),
            name=new_place["name"], category=new_place["category"] or Place.Category.ETC,
            lat=new_place["lat"], lng=new_place["lng"],
            address=new_place.get("address", report.suggested_address or report.location_text),
            floor=new_place.get("floor") if new_place.get("floor") is not None else (
                report.suggested_floor if report.suggested_floor is not None else 1
            ),
            phone=new_place.get("phone", report.suggested_phone),
        )
        report.entrance = Entrance.objects.create(place=place, name="정문", is_main=True)
        report.save(update_fields=["entrance"])
    report.review_note = review_note
    report.save(update_fields=["review_note"])
    verify_report(report, by=user)  # 커밋 후 신호 → 재판정
    return report


def reject(report, user, reason, review_note=""):
    report.review_note = review_note
    report.save(update_fields=["review_note"])
    reject_report(report, by=user, reason=reason)


def report_diff(report):
    """
    기존 공개 정보와 제보 내용 비교 (16번 '기존 공개 정보와 차이', 17번 충돌 정보 확인).
    [{label, current, proposed, conflict}] — conflict: 기존 값이 있는데 제보와 다름
    """
    current = current_values(report.target) if report.target is not None else {}
    rows = []
    for v in report.values.select_related("field").order_by("field__order"):
        before = current.get(v.field_id)
        unit = v.field.unit
        rows.append({
            "label": v.field.label,
            "current": f"{before.display_value}{unit}" if before else None,
            "current_at": before.report.observed_at if before else None,
            "proposed": f"{v.display_value}{unit}",
            "conflict": before is not None and before.value != v.value,
        })
    return rows


def recent_downgrade_places(user, now=None):
    """이 사람이 최근 7일 동안 판정을 내리는 제보를 한 서로 다른 장소 수 (기획 v2 7장 악성 제보 알림)"""
    if user is None:
        return 0
    since = (now or timezone.now()) - timedelta(days=ABUSE_DAYS)
    places = set()
    for r in Report.objects.filter(created_by=user, source=Report.Source.USER_REPORT, created_at__gte=since):
        if r.target_place is not None and report_direction(r) == DOWN:
            places.add(r.target_place.pk)
    return len(places)


def door_type_choices():
    field = FieldDefinition.objects.filter(key="door_type").first()
    return field.choices if field else []
