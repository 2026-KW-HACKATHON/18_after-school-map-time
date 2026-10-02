"""
주민 제보 폼 (와이어프레임 8번 "제보 작성").
출입구와 접근 시설을 구분해서 받는다. 기존 입구 제보의 필드 이름은 유지한다.
"""

from datetime import timedelta

from django import forms
from django.utils import timezone

from core.uploads import KeepPhotoMixin
from judgments.models import ConditionProfile
from places.facilities import ENTRANCE, ENTRANCE_KEYS, FIELD_SPECS, KIND_FIELDS
from places.models import AccessFacility, FieldDefinition, Place

from .models import PHOTO_FIX_PREFIX, Report

UNKNOWN = ""  # "모름" — 값을 넣지 않음

# 폼 칸 이름 = FieldDefinition 키 (값 저장할 때 그대로 씀)
ENTRANCE_FIELDS = ["step_height_cm", "step_count", "has_ramp", "door_width_cm", "door_type"]

REPORT_LIMIT_HOURS = 24  # 같은 사람이 같은 장소를 다시 제보할 수 있는 간격 (기획 v2 7장)


class ReportForm(KeepPhotoMixin, forms.Form):
    # 새 장소 제안 (장소를 고르지 않고 들어왔을 때만 사용)
    suggested_name = forms.CharField(label="장소 이름", max_length=100, required=False,
                                     widget=forms.TextInput(attrs={"placeholder": "예: 월계 약국, 1번 출구 카페"}))
    location_text = forms.CharField(label="위치 설명 (지도에 표시하기 어려우면 꼭 적어 주세요)", max_length=200, required=False,
                                    widget=forms.TextInput(attrs={"placeholder": "예: 월계역 2번 출구 앞 건물 1층"}))
    lat = forms.DecimalField(label="위도", required=False, min_value=-90, max_value=90,
                             max_digits=9, decimal_places=6, widget=forms.NumberInput(attrs={"step": "0.000001"}))
    lng = forms.DecimalField(label="경도", required=False, min_value=-180, max_value=180,
                             max_digits=9, decimal_places=6, widget=forms.NumberInput(attrs={"step": "0.000001"}))

    suggested_category = forms.ChoiceField(label="업종 (선택)", required=False,
                                           choices=[("", "모름")] + list(Place.Category.choices))
    suggested_address = forms.CharField(label="주소 (선택)", max_length=200, required=False)
    suggested_floor = forms.IntegerField(label="층 (선택)", required=False, min_value=-32768, max_value=32767,
                                         help_text="예: 1 = 1층, -1 = 지하 1층. 모르면 비워 주세요.")
    suggested_phone = forms.CharField(label="전화번호 (선택)", max_length=20, required=False,
                                      widget=forms.TextInput(attrs={"inputmode": "tel", "autocomplete": "tel"}))

    photo = forms.ImageField(label="입구 사진", help_text="입구, 계단, 경사로가 잘 보이게 찍어 주세요. 사람 얼굴·차 번호판은 나오지 않게 해 주세요.")

    step_height_cm = forms.DecimalField(label="입구 단차 (cm)", required=False, min_value=0, max_value=500, decimal_places=1)
    step_count = forms.IntegerField(label="계단 수 (칸)", required=False, min_value=0, max_value=50)
    has_ramp = forms.ChoiceField(label="고정 경사로", required=False,
                                 choices=[(UNKNOWN, "모름"), ("true", "있음"), ("false", "없음")])
    door_width_cm = forms.DecimalField(label="출입문 폭 (cm)", required=False, min_value=0, max_value=1000, decimal_places=1)
    door_type = forms.ChoiceField(label="출입문 형태", required=False)

    note = forms.CharField(label="추가 설명 (선택)", max_length=500, required=False,
                           widget=forms.Textarea(attrs={"rows": 3, "placeholder": "직접 경험한 내용을 적어 주세요."}))
    profiles = forms.MultipleChoiceField(label="이동 조건 (선택)", required=False, widget=forms.CheckboxSelectMultiple)
    facility_kind = forms.ChoiceField(label="무엇을 확인했나요?", required=False,
                                     choices=[(ENTRANCE, "출입구")] + list(AccessFacility.Kind.choices))
    ownership = forms.ChoiceField(label="시설 소속", required=False)
    target_reference = forms.ChoiceField(label="어느 시설인가요?", required=False)
    facility_name = forms.CharField(label="새 시설 이름 (선택)", max_length=50, required=False,
                                   help_text="예: 후문, 동쪽 엘리베이터, 2층 장애인 화장실")
    observed_on = forms.DateField(label="마지막 확인일 (선택)", required=False,
                                 widget=forms.DateInput(attrs={"type": "date"}),
                                 help_text="비우면 오늘 확인한 것으로 기록해요.")

    def __init__(self, *args, place=None, building=None, user=None, kind=ENTRANCE, ownership="PLACE", **kwargs):
        super().__init__(*args, **kwargs)
        self.place, self.building, self.user = place, building, user
        selected = self.data.get("facility_kind") if self.is_bound else kind
        self.kind = selected or ENTRANCE
        if self.kind not in KIND_FIELDS:
            self.kind = ENTRANCE  # ChoiceField still rejects the invalid submitted kind.
        scopes = [("PLACE", "가게 / 장소 전용")]
        if building or (place and place.building_id):
            scopes.append(("BUILDING", "건물 공용"))
        if building and not place:
            scopes = [("BUILDING", "건물 공용")]
        self.fields["ownership"].choices = scopes
        selected_owner = self.data.get("ownership") if self.is_bound else ownership
        self.ownership = selected_owner or scopes[0][0]
        parent_building = building or (place.building if place and place.building_id else None)
        self.parent = parent_building if self.ownership == "BUILDING" else place
        self.initial.update(facility_kind=self.kind, ownership=self.ownership)
        self.targets = {}
        targets = [("default", "주 출입구 (기존 제보)")] if self.kind == ENTRANCE and place and self.ownership == "PLACE" else []
        if self.parent:
            queryset = self.parent.entrances.all() if self.kind == ENTRANCE else self.parent.facilities.filter(
                kind=self.kind, reports__status=Report.Status.VERIFIED).distinct()
            prefix = "entrance" if self.kind == ENTRANCE else "facility"
            for target in queryset:
                ref = f"{prefix}:{target.pk}"
                self.targets[ref] = target
                targets.append((ref, target.name))
        targets.append(("new", "새 시설 제안"))
        self.fields["target_reference"].choices = targets
        self.initial["target_reference"] = targets[0][0]
        if self.kind == ENTRANCE:
            extra_keys = ENTRANCE_KEYS[len(ENTRANCE_FIELDS):]
        else:
            for key in ENTRANCE_FIELDS:
                del self.fields[key]
            extra_keys = KIND_FIELDS[self.kind]
            self.fields["photo"].label = "시설 사진"
            self.fields["photo"].help_text = "시설의 모습과 접근 경로가 보이게 찍어 주세요. 얼굴·차 번호판은 피해 주세요."
        for key in extra_keys:
            label, value_type, unit, choices, maximum = FIELD_SPECS[key]
            label = f"{label} ({unit}, 선택)" if unit else label
            if value_type == "BOOL":
                self.fields[key] = forms.ChoiceField(label=label, required=False,
                    choices=[("", "모름"), ("true", "예 / 있음"), ("false", "아니오 / 없음")])
            elif value_type == "CHOICE":
                self.fields[key] = forms.ChoiceField(label=label, required=False,
                    choices=[("", "모름")] + [(c, c) for c in choices])
            elif value_type == "NUMBER":
                field_cls = forms.IntegerField if key == "facility_step_count" else forms.DecimalField
                options = {"decimal_places": 1} if field_cls == forms.DecimalField else {}
                self.fields[key] = field_cls(label=label, required=False, min_value=0, max_value=maximum, **options)
            else:
                self.fields[key] = forms.CharField(label=label, max_length=200, required=False)
                if key == "facility_connected_floors":
                    self.fields[key].help_text = "예: 지하 1층 → 1층 → 2층. 직접 확인한 연결 층을 적어 주세요."
        self.observation_fields = [self[key] for key in KIND_FIELDS[self.kind]]
        door_type = FieldDefinition.objects.filter(key="door_type").first()
        choices = door_type.choices if door_type else []
        if "door_type" in self.fields:
            self.fields["door_type"].choices = [(UNKNOWN, "모름")] + [(c, c) for c in choices]
        self.fields["profiles"].choices = [(p.key, p.label) for p in ConditionProfile.objects.filter(is_active=True)]
        if place is not None or building is not None:
            for name in ("suggested_name", "suggested_category", "suggested_address", "suggested_floor", "suggested_phone"):
                del self.fields[name]
        self.setup_kept_photo()  # 칸을 잘못 적어 다시 보여 줄 때 올린 사진 유지

    def clean(self):
        data = super().clean()
        if (data.get("lat") is None) != (data.get("lng") is None):
            self.add_error("lat" if data.get("lat") is None else "lng", "위도와 경도를 함께 입력해 주세요.")
        if data.get("observed_on") and data["observed_on"] > timezone.localdate():
            self.add_error("observed_on", "미래 날짜는 확인일로 입력할 수 없어요.")
        if self.place is None and self.building is None and not data.get("suggested_name"):
            self.add_error("suggested_name", "장소 이름을 입력해 주세요.")
        if self.place is None and self.building is None:
            has_point = data.get("lat") is not None and data.get("lng") is not None
            if not has_point and not data.get("location_text"):
                self.add_error("lat", "지도를 눌러 위치를 표시하거나, 위치 설명을 적어 주세요.")
        values = {k: data.get(k) for k in KIND_FIELDS[self.kind]}
        if all(v in (None, UNKNOWN) for v in values.values()) and not data.get("note"):
            label = "입구" if self.kind == ENTRANCE else "시설"
            raise forms.ValidationError(f"{label} 정보를 하나 이상 고르거나, 추가 설명을 적어 주세요.")
        if self.parent is not None and self.user is not None:
            since = timezone.now() - timedelta(hours=REPORT_LIMIT_HOURS)
            recent = Report.objects.filter(created_by=self.user, created_at__gte=since).exclude(
                note__startswith=PHOTO_FIX_PREFIX)  # 사진 수정 요청은 제보 간격 제한에서 뺌
            reference = data.get("target_reference") or self.initial["target_reference"]
            target = self.targets.get(reference)
            if self.kind == ENTRANCE and reference == "default":
                limited = recent.filter(place=self.place, facility_kind="").exists() or recent.filter(entrance__place=self.place).exists()
            elif target:
                limited = recent.filter(**{"entrance" if self.kind == ENTRANCE else "facility": target}).exists()
            else:
                limited = recent.filter(**{"building" if self.ownership == "BUILDING" else "place": self.parent},
                    facility_kind=self.kind, facility_name=data.get("facility_name", "")).exists()
            if limited:
                label = "장소" if reference == "default" else "시설"
                raise forms.ValidationError(f"같은 {label}은 24시간에 한 번만 제보할 수 있어요. 확인 중인 제보가 반영될 때까지 기다려 주세요.")
        return data

    def entrance_values(self):
        """{필드 키: 값} — '모름'과 빈 칸은 뺌"""
        out = {}
        for key in KIND_FIELDS[self.kind]:
            v = self.cleaned_data.get(key)
            if v in (None, UNKNOWN):
                continue
            out[key] = v
        return out

    observation_values = entrance_values  # 기존 호출부도 그대로 지원한다.


PHOTO_FIX_REASONS = [
    ("예전 모습이에요 (공사·이전 등)", "예전 모습이에요 (공사·이전 등)"),
    ("내 얼굴이나 아는 사람 얼굴이 나와요", "내 얼굴이나 아는 사람 얼굴이 나와요"),
    ("차량 번호판이나 개인 정보가 보여요", "차량 번호판이나 개인 정보가 보여요"),
    ("기타", "기타"),
]


class PhotoFixForm(KeepPhotoMixin, forms.Form):
    """주민 → 운영자 입구 사진 수정 요청. 새 사진은 있으면 같이 (얼굴 문제면 사진 없이 '내려 주세요'만 해도 됨)"""

    reason = forms.ChoiceField(label="어떤 문제인가요?", choices=PHOTO_FIX_REASONS, widget=forms.RadioSelect)
    photo = forms.ImageField(label="새 입구 사진 (있으면)", required=False,
                             help_text="입구 정면, 문턱·계단이 보이게. 사람 얼굴·차량 번호판은 나오지 않게 찍어 주세요")
    note = forms.CharField(label="덧붙일 말 (선택)", max_length=200, required=False,
                           widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_kept_photo()
