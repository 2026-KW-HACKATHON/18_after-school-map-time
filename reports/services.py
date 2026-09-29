"""제보 상태 변경. 관리자 화면·API 어디서 처리하든 이 함수를 거친다 (처리자·시각 기록 + 신호 발송)"""

from django.db import transaction
from django.utils import timezone

from .models import Report
from .signals import report_reviewed


@transaction.atomic
def verify_report(report, by=None):
    """제보를 반영한다 → 이 값이 판정에 쓰이기 시작함"""
    _review(report, Report.Status.VERIFIED, by)


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


def _review(report, status, by, reason=""):
    report.status = status
    report.reviewed_by = by
    report.reviewed_at = timezone.now()
    report.reject_reason = reason
    report.save(update_fields=["status", "reviewed_by", "reviewed_at", "reject_reason"])
    # 커밋이 끝난 뒤에 신호를 보냄 → 재판정이 아직 저장 안 된 값을 읽는 일 방지
    transaction.on_commit(lambda: report_reviewed.send(sender=Report, report=report))
