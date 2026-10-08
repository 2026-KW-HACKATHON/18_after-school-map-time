"""
장소 데이터: 지역 → 건물 → 장소(가게) → 출입구, 그리고 접근성 필드 정의.

- 실제 접근성 값(단차 몇 cm 등)은 여기 없고 reports 앱의 AccessibilityValue에 있다.
  값은 항상 "누가·언제·어떤 근거(사진)로" 알려줬는지와 함께 저장해야 해서 제보(Report) 단위로 묶는다.
- 건물 공용 정보와 가게 정보를 나눠서 저장한다 (기획 v2 OP-4: 건물 구조 문제를 가게 책임처럼 보이지 않게).
"""

from django.core.exceptions import ValidationError
from django.db import models


def _coordinate_field(label):
    # 소수점 6자리 = 약 10cm 정밀도. 지도 마커에는 충분하고 PostGIS 없이 쓸 수 있음
    return models.DecimalField(label, max_digits=9, decimal_places=6)


class Region(models.Model):
    """
    서비스 지역 (지금은 월계1동 하나). 모든 장소 조회는 지역을 거친다 → 노원구·서울로 확장 가능 (기획 v2 8장)
    """

    code = models.SlugField("코드", max_length=30, unique=True, help_text="URL·API에 쓰는 영문 코드. 예: wolgye1")
    name = models.CharField("이름", max_length=50)
    center_lat = _coordinate_field("지도 중심 위도")
    center_lng = _coordinate_field("지도 중심 경도")
    map_level = models.PositiveSmallIntegerField("지도 확대 레벨", default=4, help_text="카카오맵 level (작을수록 확대)")
    boundary = models.JSONField("경계 (GeoJSON)", null=True, blank=True)
    is_active = models.BooleanField("서비스 중", default=True)

    class Meta:
        verbose_name = "지역"
        verbose_name_plural = "지역"

    def __str__(self):
        return self.name


class RegionScopedQuerySet(models.QuerySet):
    def in_region(self, region):
        """지역(객체 또는 코드)으로 범위를 좁힌다. 장소·건물 조회는 반드시 이걸 거친다"""
        if isinstance(region, Region):
            return self.filter(region=region)
        return self.filter(region__code=region)


class Building(models.Model):
    """건물. 공용 출입구·엘리베이터·공용 화장실 정보가 여기에 속한다"""

    region = models.ForeignKey(Region, verbose_name="지역", on_delete=models.PROTECT, related_name="buildings")
    name = models.CharField("건물 이름", max_length=100, blank=True)
    address = models.CharField("주소", max_length=200)
    lat = _coordinate_field("위도")
    lng = _coordinate_field("경도")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = RegionScopedQuerySet.as_manager()

    class Meta:
        verbose_name = "건물"
        verbose_name_plural = "건물"

    def __str__(self):
        return self.name or self.address


class Place(models.Model):
    """가게·시설. 건물 안에 있으면 building을 연결한다 (단독 건물·노점 등은 비워 둠)"""

    class Category(models.TextChoices):
        RESTAURANT = "RESTAURANT", "음식점"
        CAFE = "CAFE", "카페"
        STORE = "STORE", "편의점·마트"
        PHARMACY = "PHARMACY", "약국"
        CLINIC = "CLINIC", "병원·의원"
        PUBLIC = "PUBLIC", "공공기관"
        ETC = "ETC", "기타"

    region = models.ForeignKey(Region, verbose_name="지역", on_delete=models.PROTECT, related_name="places")
    building = models.ForeignKey(
        Building, verbose_name="건물", on_delete=models.SET_NULL, null=True, blank=True, related_name="places"
    )
    name = models.CharField("이름", max_length=100)
    category = models.CharField("유형", max_length=20, choices=Category.choices, default=Category.ETC)
    address = models.CharField("주소", max_length=200, blank=True)
    lat = _coordinate_field("위도")
    lng = _coordinate_field("경도")
    floor = models.SmallIntegerField("층", default=1, help_text="1 = 1층, -1 = 지하 1층")
    phone = models.CharField("전화번호", max_length=20, blank=True)
    is_closed = models.BooleanField("폐업", default=False, help_text="가게 정보 삭제 대신 폐업으로 처리 (기획 v2 4.4)")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = RegionScopedQuerySet.as_manager()

    class Meta:
        verbose_name = "장소"
        verbose_name_plural = "장소"

    def __str__(self):
        return self.name

    def clean(self):
        if self.building_id and self.region_id and self.building.region_id != self.region_id:
            raise ValidationError({"building": "장소와 건물의 지역이 다릅니다."})


class Entrance(models.Model):
    """
    출입구. 장소의 출입구이거나 건물 공용 출입구 둘 중 하나.
    출입구마다 따로 판정해서 "뒤쪽 문은 턱이 없어요" 같은 대체 출입구를 안내한다 (기획 v2 4.2, OP-2)
    """

    place = models.ForeignKey(
        Place, verbose_name="장소", on_delete=models.CASCADE, null=True, blank=True, related_name="entrances"
    )
    building = models.ForeignKey(
        Building, verbose_name="건물", on_delete=models.CASCADE, null=True, blank=True, related_name="entrances"
    )
    name = models.CharField("이름", max_length=50, default="정문", help_text="예: 정문, 주차장 쪽 문")
    is_main = models.BooleanField("주 출입구", default=True)
    description = models.CharField("설명", max_length=200, blank=True)

    class Meta:
        verbose_name = "출입구"
        verbose_name_plural = "출입구"
        constraints = [
            # 장소 출입구 또는 건물 출입구 중 정확히 하나 (dev-plan-v2 D1)
            models.CheckConstraint(
                condition=(
                    models.Q(place__isnull=False, building__isnull=True)
                    | models.Q(place__isnull=True, building__isnull=False)
                ),
                name="entrance_belongs_to_place_or_building",
            ),
        ]

    def __str__(self):
        owner = self.place or self.building
        return f"{owner} · {self.name}"


class AccessFacility(models.Model):
    """출입구 외 접근 시설. 사실 값·사진·위치는 검증된 Report 이력에 둔다."""

    class Kind(models.TextChoices):
        ELEVATOR = "ELEVATOR", "엘리베이터 (E/V)"
        ESCALATOR = "ESCALATOR", "에스컬레이터 (E/S)"
        STAIRS = "STAIRS", "계단"
        RAMP = "RAMP", "경사로"
        TOILET = "TOILET", "장애인 화장실"
        OTHER = "OTHER", "기타 접근 편의시설"

    place = models.ForeignKey(Place, on_delete=models.CASCADE, null=True, blank=True, related_name="facilities")
    building = models.ForeignKey(Building, on_delete=models.CASCADE, null=True, blank=True, related_name="facilities")
    kind = models.CharField("시설 종류", max_length=20, choices=Kind.choices)
    name = models.CharField("시설 이름", max_length=50)

    class Meta:
        verbose_name = "접근 시설"
        verbose_name_plural = "접근 시설"
        constraints = [models.CheckConstraint(
            condition=(models.Q(place__isnull=False, building__isnull=True)
                       | models.Q(place__isnull=True, building__isnull=False)),
            name="facility_belongs_to_place_or_building",
        )]

    def clean(self):
        if bool(self.place_id) == bool(self.building_id):
            raise ValidationError("시설은 장소 또는 건물 중 한 곳에 속해야 합니다.")

    def __str__(self):
        return f"{self.place or self.building} · {self.name}"


class FieldDefinition(models.Model):
    """
    접근성 필드 정의 (입구 단차, 출입문 폭 ...). 필드를 자유 텍스트가 아닌 이 테이블의 키로만 쓴다 (기획 v2 8장).
    새 필드 추가 = 행 추가. 초기 데이터: places/data/field_definitions.json → python manage.py seed_base
    """

    class Scope(models.TextChoices):
        PLACE = "PLACE", "장소"
        BUILDING = "BUILDING", "건물"
        ENTRANCE = "ENTRANCE", "출입구"
        FACILITY = "FACILITY", "접근 시설"

    class ValueType(models.TextChoices):
        NUMBER = "NUMBER", "숫자"
        BOOL = "BOOL", "예/아니오"
        CHOICE = "CHOICE", "선택"
        TEXT = "TEXT", "글"

    key = models.SlugField("키", max_length=50, primary_key=True)
    label = models.CharField("이름", max_length=50)
    unit = models.CharField("단위", max_length=10, blank=True)
    scope = models.CharField("대상", max_length=10, choices=Scope.choices)
    value_type = models.CharField("값 종류", max_length=10, choices=ValueType.choices)
    choices = models.JSONField("선택지", default=list, blank=True, help_text='CHOICE일 때만. 예: ["자동문", "여닫이"]')
    help_text = models.CharField("측정·확인 방법", max_length=200, blank=True)
    order = models.PositiveSmallIntegerField("표시 순서", default=0)
    is_active = models.BooleanField("사용 중", default=True)

    class Meta:
        verbose_name = "접근성 필드 정의"
        verbose_name_plural = "접근성 필드 정의"
        ordering = ["scope", "order", "key"]

    def __str__(self):
        return f"{self.label} ({self.key})"
