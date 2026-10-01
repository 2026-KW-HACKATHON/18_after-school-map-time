"""
내 활동 (기능 범위 Could "제보 포인트·배지").

- 내 제보가 지금 어떤 상태인지(확인 중 / 반영됨 / 반려 + 사유) 주민이 직접 볼 수 있게
- 기여를 숫자와 배지로 보여 준다. 배지는 좋은 쪽으로만 (기획 v2 OP-5) — 순위·경쟁은 만들지 않음
- 배지 기준은 아래 BADGES 목록 한 곳에서만 바꾼다 (코드 곳곳에 if문으로 두지 않음)
"""

from judgments.services import required_confirmations
from reports.models import Reconfirmation, Report, ReportConfirmation

# (키, 이름, 무엇을 세는지, 기준 수, 설명)
BADGES = [
    ("first_report", "첫 제보 반영", "verified_reports", 1, "알려 준 정보가 처음으로 지도에 반영됐어요"),
    ("neighbor_check", "확인 도우미", "confirmations", 3, "다른 주민의 제보를 3번 확인해 줬어요"),
    ("still_right", "지금도 맞아요 5번", "reconfirmations", 5, "가게 정보가 그대로인지 5번 확인해 줬어요"),
    ("local_mapper", "동네 지도 만들기", "verified_reports", 5, "제보 5건이 지도에 반영됐어요"),
]


def counts(user):
    reports = Report.objects.filter(created_by=user, source=Report.Source.USER_REPORT)
    return {
        "reports": reports.count(),
        "verified_reports": reports.filter(status=Report.Status.VERIFIED).count(),
        "pending_reports": reports.filter(status=Report.Status.PENDING).count(),
        "confirmations": ReportConfirmation.objects.filter(user=user).count(),
        "reconfirmations": Reconfirmation.objects.filter(user=user).count(),
    }


def badges(numbers):
    """[{"name", "description", "earned", "progress": "2/3"}] — 받은 배지 먼저"""
    rows = [
        {"key": key, "name": name, "description": desc, "earned": numbers[metric] >= goal,
         "progress": f"{min(numbers[metric], goal)}/{goal}"}
        for key, name, metric, goal, desc in BADGES
    ]
    return sorted(rows, key=lambda b: not b["earned"])


def my_reports(user, limit=30):
    """내 제보 목록. 확인 중이면 '확인 n/m명' 또는 '운영진이 확인해요'"""
    reports = (
        Report.objects.filter(created_by=user, source=Report.Source.USER_REPORT)
        .select_related("place", "entrance__place", "entrance__building", "building")
        .prefetch_related("values__field").order_by("-created_at")[:limit]
    )
    rows = []
    for r in reports:
        progress = ""
        if r.status == Report.Status.PENDING:
            required = required_confirmations(r)
            progress = f"주민 확인 {r.confirmations.count()}/{required}명" if required else "운영진이 확인해요"
        rows.append({"report": r, "place": r.target_place, "values": list(r.values.all()), "progress": progress})
    return rows


def activity(user):
    numbers = counts(user)
    return {"counts": numbers, "badges": badges(numbers), "reports": my_reports(user)}
