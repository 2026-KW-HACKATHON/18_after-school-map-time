"""사장님 기능 처리 (화면과 분리해서 테스트하기 쉽게)"""

from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone

from judgments.models import ConditionProfile
from places.models import Entrance
from reports.models import AccessibilityValue, Report
from reports.selectors import current_values

from .models import ClaimCode, OwnerClaim, PlaceViewStat, SupportProgram, VisitWish

RAMP_RATIO = 8                   # 단차 × 8 = 필요한 이동식 경사로 길이 (별표 1 12호 1/8 완화 준용)
CORRECTION_OVERDUE_DAYS = 7      # 정정 요청이 7일 넘게 처리 안 되면 운영자 알림 (기획 v2 4.3)


class OwnerError(Exception):
    pass


# ── 인증 (기획 v2 4.1) ─────────────────────────────────────


@transaction.atomic
def claim_with_code(user, raw_code):
    """6자리 코드 입력 → 인증 신청(확인 중). 코드는 1회용"""
    code = ClaimCode.objects.select_for_update().filter(code=raw_code.strip()).first()
    if code is None:
        raise OwnerError("코드를 찾을 수 없어요. 답사 때 받은 6자리 숫자를 다시 확인해 주세요.")
    if code.is_used:
        raise OwnerError("이미 사용된 코드예요. 운영진에게 새 코드를 요청해 주세요.")
    target = {"place": code.place} if code.place_id else {"building": code.building}
    if OwnerClaim.objects.filter(user=user, **target).exclude(status=OwnerClaim.Status.REJECTED).exists():
        raise OwnerError("이미 신청했거나 인증된 곳이에요.")
    claim = OwnerClaim.objects.create(
        user=user, code=code, status=OwnerClaim.Status.PENDING,
        role=OwnerClaim.Role.OPERATOR if code.place_id else OwnerClaim.Role.BUILDING_OWNER, **target,
    )
    code.used_at = timezone.now()
    code.save(update_fields=["used_at"])
    return claim


# ── 사장님 제보: 도움 제공 선언·정정 요청 (기획 v2 4.2·4.3) ───────


def main_entrance(place):
    entrance = place.entrances.filter(is_main=True).first() or place.entrances.first()
    return entrance or Entrance.objects.create(place=place, name="정문", is_main=True)


def open_correction_fields(target):
    """진행 중인 사장님 제보가 있는 필드 → 같은 필드는 끝나야 새로 요청 가능"""
    from reports.selectors import _target_filter

    return set(
        AccessibilityValue.objects.filter(
            report__status=Report.Status.PENDING, report__source=Report.Source.OWNER, **_target_filter(target)
        ).values_list("field_id", flat=True)
    )


@transaction.atomic
def submit_owner_report(user, target, values, photo, note=""):
    """
    사장님 출처 제보 (확인 중). 사진 필수 — 사장님 선언만으로 판정이 올라가지 않게 (기획 v2 4.2)
    target: 장소(가게 안 값) 또는 출입구(입구 값)
    """
    busy = open_correction_fields(target) & set(values)
    if busy:
        raise OwnerError("같은 항목의 요청이 아직 확인 중이에요. 처리된 뒤에 다시 요청해 주세요.")
    key = "entrance" if isinstance(target, Entrance) else "place"
    report = Report.objects.create(
        source=Report.Source.OWNER, status=Report.Status.PENDING, created_by=user, photo=photo, note=note,
        **{key: target},
    )
    for field_key, raw in values.items():
        value = AccessibilityValue(report=report, field_id=field_key)
        value.set_value(raw)
        value.full_clean()
        value.save()
    return report


# ── 가고 싶어요 (기획 v2 4.5) ─────────────────────────────────


def toggle_wish(user, place, profile):
    """누르면 추가, 다시 누르면 취소. 반환: 지금 눌린 상태인지"""
    wish, created = VisitWish.objects.get_or_create(user=user, place=place, profile=profile)
    if not created:
        wish.delete()
    return created


# ── 사장님 대시보드 (기획 v2 4.5) ─────────────────────────────


def ramp_guide(place):
    """입구 단차에 맞는 이동식 경사로 길이 (단차 × 8). 단차가 없거나 모르면 None"""
    values = current_values(main_entrance(place))
    step = values.get("step_height_cm")
    if step is None or step.value is None or step.value <= 0:
        return None
    height = Decimal(step.value)
    return {"step_cm": height.normalize(), "ramp_cm": (height * RAMP_RATIO).normalize()}


def dashboard(place, today=None):
    today = today or timezone.localdate()
    month_start = today.replace(day=1)
    profiles = list(ConditionProfile.objects.filter(is_active=True))
    views = dict(
        PlaceViewStat.objects.filter(place=place, date__gte=month_start)
        .values_list("profile_id").annotate(total=Sum("count"))
    )
    wishes = dict(VisitWish.objects.filter(place=place).values_list("profile_id").annotate(n=Count("id")))
    return {
        "rows": [{"profile": p, "views": views.get(p.key, 0), "wishes": wishes.get(p.key, 0)} for p in profiles],
        "total_views": sum(views.values()),
        "total_wishes": sum(wishes.values()),
        "ramp": ramp_guide(place),
        "programs": SupportProgram.objects.filter(region=place.region, is_active=True),
        "my_reports": Report.objects.filter(Q(place=place) | Q(entrance__place=place), source=Report.Source.OWNER)
        .prefetch_related("values__field").order_by("-created_at")[:20],
    }
