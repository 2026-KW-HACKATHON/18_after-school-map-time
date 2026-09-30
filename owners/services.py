"""사장님 기능 처리 (화면과 분리해서 테스트하기 쉽게)"""

from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone

from judgments.constants import IMPROVEMENT_RANK, display
from judgments.engine import judge
from judgments.models import ConditionProfile, Judgment, Outcome, RuleSet
from judgments.services import is_photo_request
from places.models import Building, Entrance
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


def building_main_entrance(building):
    entrance = building.entrances.filter(is_main=True).first() or building.entrances.first()
    return entrance or Entrance.objects.create(building=building, name="공용 입구", is_main=True)


def _target_key(target):
    """제보 대상 칸 이름: 출입구·건물·가게"""
    if isinstance(target, Entrance):
        return "entrance"
    if isinstance(target, Building):
        return "building"
    return "place"


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
    key = _target_key(target)
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
        "judgments": place_judgments(place),
        "programs": SupportProgram.objects.filter(region=place.region, is_active=True),
        "my_reports": sent_requests(Q(place=place) | Q(entrance__place=place)),
        "photo_pending": has_pending_photo_request(place),
    }


def place_judgments(place):
    """지금 지도에 보이는 판정 (이동 조건별 문구 + 사실 한 줄) — 사장님이 '손님에게 어떻게 보이는지' 확인"""
    judgments = {j.profile_id: j for j in Judgment.objects.filter(place=place)}
    rows = []
    for profile in ConditionProfile.objects.filter(is_active=True):
        j = judgments.get(profile.key)
        rows.append({"profile": profile, "display": display(j.result if j else Outcome.UNKNOWN),
                     "reason": j.reason if j else ""})
    return rows


def sent_requests(condition):
    """보낸 요청 목록 (종류 문구 포함)"""
    reports = (Report.objects.filter(condition, source=Report.Source.OWNER)
               .prefetch_related("values__field").order_by("-created_at")[:20])
    return [{"report": r, "kind": "사진 교체 요청" if is_photo_request(r) else ""} for r in reports]


# ── 입구 사진 교체 요청 (기획 v2 4.4) ────────────────────────

PHOTO_REASONS = [
    ("간판·상호가 크게 나와요", "간판·상호가 크게 나와요"),
    ("사람 얼굴이 나와요", "사람 얼굴이 나와요"),
    ("예전 모습이에요 (공사·이전 등)", "예전 모습이에요 (공사·이전 등)"),
    ("기타", "기타"),
]


def has_pending_photo_request(place):
    return Report.objects.filter(
        entrance__place=place, source=Report.Source.OWNER, status=Report.Status.PENDING, values__isnull=True,
    ).exists()


@transaction.atomic
def submit_photo_request(user, place, photo, reason, note=""):
    """
    입구 사진 교체 요청. 값 없이 사진만 담은 사장님 제보(확인 중)로 넣고, 운영자만 승인한다
    (얼굴·번호판 확인 — judgments.services.required_confirmations). 가게 정보 '삭제' 요청은 받지 않는다.
    """
    if has_pending_photo_request(place):
        raise OwnerError("사진 교체 요청이 아직 확인 중이에요. 처리된 뒤에 다시 요청해 주세요.")
    return Report.objects.create(
        source=Report.Source.OWNER, status=Report.Status.PENDING, created_by=user, photo=photo,
        entrance=main_entrance(place), note=" · ".join(filter(None, [f"사진 교체 요청: {reason}", note]))[:500],
    )


# ── 건물주 (기획 v2 5장) ──────────────────────────────────────

# 개선 시뮬레이션 시나리오: 건물 공용 입구·건물 값에 가상 값을 넣고 판정 엔진으로 다시 계산한다 (기준값은 규칙 데이터 그대로)
#  entrance_values: 건물 공용 출입구에 넣을 값 / building_values: 건물 값 (엘리베이터 등)
#  only_upper_floor: 2층 이상·지하 가게가 있을 때만 보여 줌 (1층 가게만 있는 건물에 엘리베이터 안내는 의미 없음)
SCENARIOS = [
    {"key": "ramp", "title": "건물 공용 입구에 고정 경사로를 설치하면", "entrance_values": {"has_ramp": True}},
    {"key": "elevator", "title": "엘리베이터를 설치하면", "building_values": {"elevator": True}, "only_upper_floor": True},
    {"key": "both", "title": "입구 경사로와 엘리베이터를 모두 설치하면", "entrance_values": {"has_ramp": True},
     "building_values": {"elevator": True}, "only_upper_floor": True},
]


def simulate(building, scenario):
    """
    건물 입구 개선 시 건물 안 가게들의 판정 변화 (기획 v2 5.2).
    반환: [{"profile", "before", "after", "improved": [가게 이름]}]
      before/after = "들어갈 수 있어요"(ACCESSIBLE) 가게 수, improved = 한 단계라도 나아지는 가게
    """
    rule_set = RuleSet.active()
    entrances = list(building.entrances.all())
    places = list(building.places.filter(is_closed=False))
    if rule_set is None or not places or (scenario.get("entrance_values") and not entrances):
        return []
    overrides = {e: scenario.get("entrance_values", {}) for e in entrances}
    overrides[building] = scenario.get("building_values", {})
    rows = []
    for profile in ConditionProfile.objects.filter(is_active=True):
        before = after = 0
        improved = []
        for place in places:
            b = judge(place, profile, rule_set).outcome
            a = judge(place, profile, rule_set, overrides=overrides).outcome
            before += b == Outcome.ACCESSIBLE
            after += a == Outcome.ACCESSIBLE
            if IMPROVEMENT_RANK.get(a, 0) > IMPROVEMENT_RANK.get(b, 0):
                improved.append(place.name)
        rows.append({"profile": profile, "before": before, "after": after, "improved": improved})
    return rows


def building_overview(building):
    """건물주 화면·공유 페이지 공통: 건물 안 가게 판정 + 개선 시뮬레이션"""
    places = list(building.places.filter(is_closed=False).order_by("floor", "name"))
    upper = any(p.floor != 1 for p in places)
    return {
        "building": building,
        "places": [{"place": p, "judgments": place_judgments(p)} for p in places],
        "simulations": [{"title": s["title"], "rows": simulate(building, s)}
                        for s in SCENARIOS if upper or not s.get("only_upper_floor")],
        "programs": SupportProgram.objects.filter(region=building.region, is_active=True),
    }


# ── 상단 메뉴 '내 가게' ──────────────────────────────────────


def owner_menu(user):
    """
    인증 신청이 있는 사람에게 상단 메뉴 링크. 승인된 곳이 하나뿐이면 그 화면으로 바로 간다.
    반환: None 또는 {"url", "label", "pending"}
    """
    from django.urls import reverse

    claims = list(OwnerClaim.objects.filter(user=user).exclude(status=OwnerClaim.Status.REJECTED)
                  .values_list("status", "place_id", "building_id"))
    if not claims:
        return None
    approved = [c for c in claims if c[0] == OwnerClaim.Status.APPROVED]
    url = reverse("owners:home")
    if len(claims) == 1 and approved:
        _, place_id, building_id = approved[0]
        url = (reverse("owners:dashboard", args=[place_id]) if place_id
               else reverse("owners:building", args=[building_id]))
    label = "내 건물" if all(c[2] for c in claims) else "내 가게"
    return {"url": url, "label": label, "pending": not approved}
