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


def _review(report, status, by, reason=""):
    report.status = status
    report.reviewed_by = by
    report.reviewed_at = timezone.now()
    report.reject_reason = reason
    report.save(update_fields=["status", "reviewed_by", "reviewed_at", "reject_reason"])
    # 커밋이 끝난 뒤에 신호를 보냄 → 재판정이 아직 저장 안 된 값을 읽는 일 방지
    transaction.on_commit(lambda: report_reviewed.send(sender=Report, report=report))
