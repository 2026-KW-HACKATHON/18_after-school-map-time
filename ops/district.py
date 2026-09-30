"""
구청용 지역 집계 (기획 v2 8장 '구청 대시보드', 6.1 지원사업 대상 발굴, 9장 B2G).

- 운영자만 본다. 가게·거리 단위 "접근성 나쁜 곳" 공개 랭킹은 만들지 않는다 (기획 v2 3.2, OP-7)
- 지원사업 검토 목록 = 혼자 들어가기 어려운 가게 중 수요(가고 싶어요·조회)나 개선 의지(사장님 인증)가 있는 곳.
  구청이 찾는 "의지 있는 가게"와 "수요가 있는 가게"를 데이터로 보여 준다 (6.1)
"""

from decimal import Decimal

from django.db.models import Count, Sum
from django.utils import timezone

from judgments.constants import display
from judgments.models import ConditionProfile, Judgment, Outcome
from owners.models import OwnerClaim, PlaceViewStat, VisitWish
from owners.services import RAMP_RATIO
from places.models import Place
from reports.selectors import current_values

OUTCOME_ORDER = [Outcome.ACCESSIBLE, Outcome.CONDITIONAL, Outcome.DIFFICULT, Outcome.UNKNOWN]


def _open_places(region):
    return Place.objects.in_region(region).filter(is_closed=False)


def outcome_distribution(region):
    """이동 조건별 판정 분포 [{"profile", "cells": [{"label", "count"}], "total"}]. 판정이 없는 곳은 미확인"""
    places = _open_places(region)
    total = places.count()
    rows = []
    for profile in ConditionProfile.objects.filter(is_active=True):
        counts = dict(
            Judgment.objects.filter(place__in=places, profile=profile)
            .values_list("result").annotate(n=Count("id"))
        )
        counts[Outcome.UNKNOWN] = total - sum(v for k, v in counts.items() if k != Outcome.UNKNOWN)
        rows.append({
            "profile": profile,
            "cells": [{"label": display(o)["label"], "count": counts.get(o, 0)} for o in OUTCOME_ORDER],
            "total": total,
        })
    return rows


def improved_places(region):
    """'개선 완료' 배지가 붙은 가게 수 (판정이 한 단계 이상 올라간 뒤 유지 중)"""
    judgments = Judgment.objects.filter(place__in=_open_places(region), improved_at__isnull=False)
    return len({j.place_id for j in judgments if j.has_improved_badge})


def support_candidates(region, today=None):
    """
    지원사업 검토 목록: 어떤 이동 조건으로든 '혼자 들어가기 어려워요'인 가게.
    순서: 개선 의지(사장님·건물주 인증) → 가고 싶어요 → 이번 달 조회 (공개하지 않는 내부 검토용)
    """
    today = today or timezone.localdate()
    places = list(
        _open_places(region).filter(judgments__result=Outcome.DIFFICULT).distinct().select_related("building")
    )
    ids = [p.pk for p in places]
    wishes = dict(VisitWish.objects.filter(place_id__in=ids).values_list("place_id").annotate(n=Count("id")))
    views = dict(
        PlaceViewStat.objects.filter(place_id__in=ids, date__gte=today.replace(day=1))
        .values_list("place_id").annotate(n=Sum("count"))
    )
    approved = OwnerClaim.objects.filter(status=OwnerClaim.Status.APPROVED)
    owner_places = set(approved.filter(place_id__in=ids).values_list("place_id", flat=True))
    owner_buildings = set(approved.filter(building__isnull=False).values_list("building_id", flat=True))
    difficult = {}
    for j in Judgment.objects.filter(place_id__in=ids, result=Outcome.DIFFICULT).select_related("profile"):
        difficult.setdefault(j.place_id, []).append(j)

    rows = []
    for place in places:
        # 주 출입구 (조회만 — 없으면 만들지 않음)
        entrance = place.entrances.order_by("-is_main", "id").first()
        step = current_values(entrance).get("step_height_cm") if entrance else None
        step_cm = Decimal(step.value).normalize() if step and step.value else None
        judgments = sorted(difficult.get(place.pk, []), key=lambda j: j.profile.order)
        rows.append({
            "place": place,
            "profiles": [j.profile.label for j in judgments],
            "reason": next((j.reason for j in judgments if j.reason), ""),
            "wishes": wishes.get(place.pk, 0),
            "views": views.get(place.pk, 0),
            "owner": place.pk in owner_places,
            "building_owner": place.building_id in owner_buildings,
            "step_cm": step_cm,
            "ramp_cm": (step_cm * RAMP_RATIO).normalize() if step_cm else None,
        })
    rows.sort(key=lambda r: (-(r["owner"] or r["building_owner"]), -r["wishes"], -r["views"], r["place"].name))
    return rows


def summary(region):
    places = _open_places(region)
    return {
        "places": places.count(),
        "improved": improved_places(region),
        "wishes": VisitWish.objects.filter(place__in=places).count(),
        "owners": OwnerClaim.objects.filter(status=OwnerClaim.Status.APPROVED).count(),
    }


CSV_HEADER = ["가게", "주소", "층", "어려운 이동 조건", "사실", "입구 단차(cm)", "필요한 경사로 길이(cm, 단차×8)",
              "가고 싶어요", "이번 달 조회", "사장님 인증", "건물주 인증"]


def candidate_csv_rows(rows):
    for r in rows:
        p = r["place"]
        yield [p.name, p.address, p.floor, " · ".join(r["profiles"]), r["reason"], r["step_cm"] or "",
               r["ramp_cm"] or "", r["wishes"], r["views"], "예" if r["owner"] else "", "예" if r["building_owner"] else ""]
