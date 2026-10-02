"""제보 상태 변경. 관리자 화면·API 어디서 처리하든 이 함수를 거친다 (처리자·시각 기록 + 신호 발송)"""

from django.db import transaction
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from .models import Report
from .signals import report_reviewed


@transaction.atomic
def verify_report(report, by=None):
    """제보를 반영한다 → 이 값이 판정에 쓰이기 시작함"""
    Report.objects.select_for_update().get(pk=report.pk)
    report.refresh_from_db()
    if report.status == Report.Status.VERIFIED:
        return report
    if report.is_facility_report:
        if by is None or not by.is_staff:
            raise PermissionDenied("시설 제보는 운영자가 검토해야 합니다.")
        if report.is_facility_proposal:
            _create_proposed_facility(report)
    _review(report, Report.Status.VERIFIED, by)
    return report


def _create_proposed_facility(report):
    """운영자 승인 시에만 시설 식별자를 만든다. 기존 입구·시설은 변경하지 않는다."""
    from places.models import AccessFacility, Entrance

    report.full_clean()
    parent = report.place or report.building
    if parent is None:
        raise ValidationError("새 장소 등록 화면에서 장소를 먼저 확인해 주세요.")
    parent_key = "place" if report.place_id else "building"
    if report.facility_kind == "ENTRANCE":
        target = Entrance.objects.create(**{parent_key: parent}, name=report.facility_name or "정문",
                                         is_main=not parent.entrances.exists())
        report.entrance = target
        target_field = "entrance"
    else:
        target = AccessFacility(**{parent_key: parent}, kind=report.facility_kind,
                                name=report.facility_name or dict(AccessFacility.Kind.choices)[report.facility_kind])
        target.full_clean()
        target.save()
        report.facility = target
        target_field = "facility"
    report.place = report.building = None
    report.save(update_fields=["place", "building", target_field])


@transaction.atomic
def reject_report(report, by=None, reason=""):
    _review(report, Report.Status.REJECTED, by, reason)


class ConfirmationError(Exception):
    pass


@transaction.atomic
def confirm_report(report, user, required):
    """
    다른 주민의 "맞아요" 확인. 확인 수가 required 이상이 되면 자동 반영한다.
    required(필요한 확인 수)는 판정 방향에 따라 부르는 쪽이 정한다
    (judgments.services.required_confirmations: 하향 2명, 그 외 1명 — 기획 v2 7장)
    반환: 반영됐으면 True
    """
    from .models import ReportConfirmation

    if report.is_facility_report or required is None:
        raise ConfirmationError("시설 제보는 운영진이 확인해요.")
    if report.status != Report.Status.PENDING:
        raise ConfirmationError("이미 처리된 제보예요.")
    if report.created_by_id == user.pk:
        raise ConfirmationError("본인이 올린 제보는 확인할 수 없어요.")
    _, created = ReportConfirmation.objects.get_or_create(report=report, user=user)
    if not created:
        raise ConfirmationError("이미 확인한 제보예요.")

    count = report.confirmations.count()
    if count >= required:
        report.review_note = f"주민 확인 {count}명으로 자동 반영"
        report.save(update_fields=["review_note"])
        verify_report(report, by=None)
        return True
    return False


RECONFIRM_WINDOW_DAYS = 30  # 상세 화면 "최근 30일 동안 주민 N명이 확인했어요"


def place_report_filter(place):
    """이 장소 화면에 나오는 제보: 장소·장소 출입구·건물·건물 출입구"""
    from django.db.models import Q

    q = Q(place=place) | Q(entrance__place=place) | Q(facility__place=place)
    if place.building_id:
        q |= Q(building_id=place.building_id) | Q(entrance__building_id=place.building_id) | Q(facility__building_id=place.building_id)
    return q


def has_public_info(place):
    """재확인할 공개 정보가 있는지 (반영된 값이 하나라도 있어야 '지금도 맞아요'를 누를 수 있음)"""
    from django.db.models import Q

    return Report.objects.filter(place_report_filter(place), Q(values__isnull=False) | Q(facility__isnull=False),
                                 status=Report.Status.VERIFIED).exists()


def last_checked_at(place):
    """
    최근 확인 시각 = 반영된 값의 가장 최근 확인 시각과 '지금도 맞아요' 중 늦은 쪽.
    반영된 값이 하나도 없으면 None (확인할 정보가 없으므로 '지금도 맞아요'도 세지 않음)
    """
    from django.db.models import Max, Q

    last = (Report.objects.filter(place_report_filter(place), Q(values__isnull=False) | Q(facility__isnull=False),
                                  status=Report.Status.VERIFIED)
            .aggregate(last=Max("observed_at"))["last"])
    if last is None:
        return None
    reconfirmed = place.reconfirmations.aggregate(last=Max("created_at"))["last"]
    return max(last, reconfirmed) if reconfirmed else last


def reconfirm_place(place, user):
    """
    "지금도 맞아요" 기록. 판정·값은 바꾸지 않고 최근 확인일만 갱신 (reports.models.Reconfirmation 참고).
    같은 사람·같은 가게는 하루 한 번
    """
    from .models import Reconfirmation

    if not has_public_info(place):
        raise ConfirmationError("아직 확인할 정보가 없어요. 제보로 알려 주세요.")
    if Reconfirmation.objects.filter(place=place, user=user, created_at__date=timezone.localdate()).exists():
        raise ConfirmationError("오늘은 이미 확인해 주셨어요.")
    return Reconfirmation.objects.create(place=place, user=user)


def recent_reconfirmations(place, days=RECONFIRM_WINDOW_DAYS):
    """최근 N일 동안 '지금도 맞아요'를 누른 서로 다른 사람 수"""
    from datetime import timedelta

    since = timezone.now() - timedelta(days=days)
    return place.reconfirmations.filter(created_at__gte=since).values("user").distinct().count()


def _review(report, status, by, reason=""):
    report.status = status
    report.reviewed_by = by
    report.reviewed_at = timezone.now()
    report.reject_reason = reason
    report.save(update_fields=["status", "reviewed_by", "reviewed_at", "reject_reason"])
    # 커밋이 끝난 뒤에 신호를 보냄 → 재판정이 아직 저장 안 된 값을 읽는 일 방지
    transaction.on_commit(lambda: report_reviewed.send(sender=Report, report=report))
