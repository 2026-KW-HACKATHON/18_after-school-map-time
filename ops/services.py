"""운영자 작업. 화면(views)과 분리해서 테스트하기 쉽게 둔다."""

from datetime import datetime, time, timedelta
from collections import Counter
from decimal import Decimal

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


def facility_inventory(place, include_reports=False):
    """장소 전용·건물 공용 시설을 운영자에게 구분해 보여 준다. 조회만 하고 값은 바꾸지 않는다."""
    sections = []
    for parent, label in ((place, "장소 전용"), (place.building, "건물 공용")):
        if parent is None:
            continue
        rows = []
        for target in [*parent.entrances.all(), *parent.facilities.all()]:
            row = {"name": target.name, "kind_label": "출입구" if isinstance(target, Entrance) else target.get_kind_display()}
            if include_reports:
                row["report"] = target.reports.order_by("-observed_at", "-created_at", "-pk").first()
            rows.append(row)
        pending = (parent.reports.filter(status=Report.Status.PENDING, facility__isnull=True)
                   .exclude(facility_kind="").order_by("-created_at")) if include_reports else []
        sections.append({
            "label": label, "parent": parent, "rows": rows, "pending": pending,
            "counts": [{"label": kind, "count": count} for kind, count in
                       Counter(row["kind_label"] for row in rows).items()],
        })
    return sections


@transaction.atomic
@transaction.atomic
def delete_reports(reports):
    """
    제보 기록 삭제 (운영자 정리용). 값·주민 확인은 함께 지워지고, 사진 파일은 저장이 끝난 뒤 지운다.
    지도에 반영됐던(VERIFIED) 기록이면 그 값이 빠지므로 영향받는 장소를 다시 판정한다.
    반환: 지운 기록 수
    """
    from judgments.receivers import affected_places

    reports = list(reports)
    places, photos = {}, []
    for report in reports:
        if report.status == Report.Status.VERIFIED:
            for place in affected_places(report):
                places[place.pk] = place
        if report.photo:
            photos.append((report.photo.storage, report.photo.name))
    Report.objects.filter(pk__in=[r.pk for r in reports]).delete()
    for place in places.values():
        recompute_place(place)
    transaction.on_commit(lambda: [storage.delete(name) for storage, name in photos])
    return len(reports)


def delete_place(place):
    """장소와 연결된 기록을 기존 FK 삭제 규칙에 따라 한 트랜잭션으로 삭제한다."""
    place.delete()


def entrance_form_initial(place):
    """장소 수정 폼에 검증된 주 출입구 값을 채운다. 조회만으로 출입구를 만들지 않는다."""
    entrance = place.entrances.filter(is_main=True).first() or place.entrances.first()
    if entrance is None:
        return {}
    initial = {}
    # 이동 조건은 관측값이 아닌 제보 메타데이터다. 최근 작성된 검증 기록의 선택을 표시한다.
    report = entrance.reports.filter(
        status=Report.Status.VERIFIED, source__in=[Report.Source.USER_REPORT, Report.Source.TEAM_SURVEY],
    ).order_by("-created_at", "-pk").first()
    initial["profiles"] = report.profiles if report else []
    for key, value in current_values(entrance).items():
        if key in ENTRANCE_KEYS:
            raw = value.value
            if isinstance(raw, Decimal):
                # DB는 소수 2자리, 입력 폼은 1자리다. 90.00을 그대로 재제출하면 검증에 걸린다.
                raw = Decimal(f"{raw.normalize():f}")
            # ChoiceField는 bool이 아닌 문자열을 사용한다. 0·False도 유효한 값이다.
            initial[key] = ("true" if raw else "false") if isinstance(raw, bool) else raw
    return initial


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
    previous = entrance_form_initial(place)
    previous_profiles = previous.get("profiles", [])
    # 체크를 모두 해제한 제출과 이동 조건 칸이 없는 기존 클라이언트의 제출을 구분한다.
    profiles_submitted = "profiles" in form.data or form.data.get("profiles_present") == "1"
    profiles = data["profiles"] if profiles_submitted else previous_profiles
    profiles_changed = set(profiles) != set(previous_profiles)
    if not any(data.get(key) for key in ("source_note", "observed_on", "memo")):
        # 자동으로 채운 값을 그대로 제출한 경우 원래 제보의 출처·확인 시각을 유지한다.
        # 출처/확인일/메모를 입력한 명시적 재확인은 같은 값이어도 새 이력으로 남긴다.
        entrance_values = {key: raw for key, raw in entrance_values.items()
                           if key not in previous or raw != previous[key]}
    if entrance_values or profiles_changed:
        report = _survey_report(user, observed_at, note, entrance=main_entrance(place), profiles=profiles)
        _save_values(report, entrance_values)
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
    Report.objects.select_for_update().get(pk=report.pk)
    report.refresh_from_db()
    if report.status == Report.Status.VERIFIED:
        return report
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
        if report.facility_kind:
            report.place = place
            report.save(update_fields=["place"])
        else:
            report.entrance = Entrance.objects.create(place=place, name="정문", is_main=True)
            report.save(update_fields=["entrance"])
    report.review_note = review_note
    report.save(update_fields=["review_note"])
    report = verify_report(report, by=user)  # 커밋 후 신호 → 재판정
    return report


def remove_current_photo(entrance, keep=None):
    """
    지금 상세 화면에 보이는 입구 사진(검증된 제보 중 가장 최근 사진)을 내린다 — 파일까지 지움 (얼굴·번호판).
    keep: 지우지 않을 제보 (지금 승인하는 요청의 새 사진). 내린 사진이 있으면 그 제보를 돌려준다
    """
    shown = (Report.objects.filter(entrance=entrance, status=Report.Status.VERIFIED).exclude(photo="")
             .exclude(pk=getattr(keep, "pk", None)).order_by("-observed_at", "-created_at", "-id").first())
    if shown is None:
        return None
    shown.photo.delete(save=False)
    Report.objects.filter(pk=shown.pk).update(photo="")
    return shown


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
