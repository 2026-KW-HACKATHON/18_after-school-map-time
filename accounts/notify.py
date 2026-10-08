"""
서비스 안 알림 만들기 — 알림 문구는 여기 한 곳에서 관리한다.

언제 만드나
- 주민 제보가 반영·반려됐을 때 → 제보한 주민 (reports.signals.report_reviewed)
- 사장님·건물주 요청(선언·정정·사진 교체)이 반영·반려됐을 때 → 요청한 사장님·건물주
- 사장님·건물주 인증이 승인·반려됐을 때 → 신청한 사람 (owners.models.OwnerClaim.review)
- '가고 싶어요'를 누른 가게의 판정이 좋아졌을 때 → 누른 주민 (judgments.signals.place_improved, owners/receivers.py)
팀 답사 기록·운영자 본인의 처리는 알림을 만들지 않는다.
"""

from django.urls import reverse

from .models import Notification


def notify(user, kind, message, url=""):
    if user is None or not user.is_active:
        return None
    return Notification.objects.create(user=user, kind=kind, message=message[:200], url=url[:200])


def _place_url(report):
    place = report.target_place
    return reverse("places:detail", args=[place.pk]) if place and not place.is_closed else ""


def report_reviewed(report):
    """제보·사장님 요청이 처리됐을 때 (반영 VERIFIED / 반려 REJECTED)"""
    from reports.models import PHOTO_FIX_PREFIX, Report

    author = report.created_by
    if author is None or report.reviewed_by_id == author.pk:
        return None  # 작성자 없음, 또는 운영자가 자기 기록을 처리
    verified = report.status == Report.Status.VERIFIED
    reason = f" — {report.reject_reason}" if report.reject_reason and not verified else ""
    target = report.target_place.name if report.target_place else report.target_label
    if report.source == Report.Source.USER_REPORT:
        if report.note.startswith(PHOTO_FIX_PREFIX):
            message = (f"{target} 사진 수정 요청을 처리했어요." if verified
                       else f"{target} 사진 수정 요청이 반려됐어요{reason}")
        else:
            message = f"{target} 제보가 지도에 반영됐어요." if verified else f"{target} 제보가 반영되지 않았어요{reason}"
        return notify(author, Notification.Kind.REPORT, message, _place_url(report) or reverse("accounts:me"))
    if report.source == Report.Source.OWNER:
        message = f"{target}에 보낸 요청이 반영됐어요." if verified else f"{target}에 보낸 요청이 반려됐어요{reason}"
        place = report.target_place
        url = reverse("owners:dashboard", args=[place.pk]) if place else reverse("owners:home")
        return notify(author, Notification.Kind.OWNER_REQUEST, message, url)
    return None


def claim_reviewed(claim):
    """사장님·건물주 인증 결과"""
    from owners.models import OwnerClaim

    target = claim.place or claim.building
    if claim.status == OwnerClaim.Status.APPROVED:
        url = (reverse("owners:dashboard", args=[claim.place_id]) if claim.place_id
               else reverse("owners:building", args=[claim.building_id]))
        return notify(claim.user, Notification.Kind.CLAIM, f"{target} 인증이 승인됐어요. 이제 사장님 화면을 쓸 수 있어요.", url)
    reason = f" — {claim.reject_reason}" if claim.reject_reason else ""
    return notify(claim.user, Notification.Kind.CLAIM, f"{target} 인증이 반려됐어요{reason}", reverse("owners:home"))


def wish_place_improved(user, place, profile, label):
    """가고 싶어요를 누른 가게가 좋아졌을 때 (기획 v2 6.2 개선 완료 알림)"""
    return notify(user, Notification.Kind.WISH, f"가고 싶어요 누른 '{place.name}' — {profile.label} 기준 '{label}'로 바뀌었어요.",
                  reverse("places:detail", args=[place.pk]))
