"""제보가 반영·반려되면 영향을 받는 장소를 다시 판정한다"""

from django.dispatch import receiver

from reports.signals import report_reviewed

from .engine import recompute_place


def affected_places(report):
    if report.place_id:
        return [report.place]
    if report.entrance_id:
        entrance = report.entrance
        if entrance.place_id:
            return [entrance.place]
        return list(entrance.building.places.all())
    if report.building_id:
        return list(report.building.places.all())  # 건물 정보가 바뀌면 건물 안 가게 전부
    return []


@receiver(report_reviewed, dispatch_uid="judgments_recompute_on_review")
def recompute_on_review(sender, report, **kwargs):
    for place in affected_places(report):
        recompute_place(place)
