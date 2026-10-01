"""제보·사장님 요청 처리 결과 → 작성자에게 알림 (accounts/notify.py)"""

from django.dispatch import receiver

from reports.signals import report_reviewed

from . import notify


@receiver(report_reviewed, dispatch_uid="accounts_notify_on_review")
def notify_on_review(sender, report, **kwargs):
    notify.report_reviewed(report)
