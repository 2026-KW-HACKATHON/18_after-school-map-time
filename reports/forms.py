"""
주민 제보 폼 (와이어프레임 8번 "제보 작성").
입구 정보만 받는다 — 와이어프레임의 항목(입구 턱 높이·경사로·출입문 형태·폭)과 같고, "들어갈 수 있나?"의 핵심.
"""

from datetime import timedelta

from django import forms
from django.utils import timezone

from judgments.models import ConditionProfile
from places.models import FieldDefinition, Place

from .models import Report

UNKNOWN = ""  # "모름" — 값을 넣지 않음

# 폼 칸 이름 = FieldDefinition 키 (값 저장할 때 그대로 씀)
ENTRANCE_FIELDS = ["step_height_cm", "step_count", "has_ramp", "door_width_cm", "door_type"]

REPORT_LIMIT_HOURS = 24  # 같은 사람이 같은 장소를 다시 제보할 수 있는 간격 (기획 v2 7장)


class ReportForm(forms.Form):
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

    def __init__(self, *args, place=None, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.place, self.user = place, user
        door_type = FieldDefinition.objects.filter(key="door_type").first()
        choices = door_type.choices if door_type else []
        self.fields["door_type"].choices = [(UNKNOWN, "모름")] + [(c, c) for c in choices]
        self.fields["profiles"].choices = [(p.key, p.label) for p in ConditionProfile.objects.filter(is_active=True)]
        if place is not None:
            for name in ("suggested_name", "location_text", "suggested_category", "suggested_address", "suggested_floor", "suggested_phone"):
                del self.fields[name]

    def clean(self):
        data = super().clean()
        if (data.get("lat") is None) != (data.get("lng") is None):
            self.add_error("lat" if data.get("lat") is None else "lng", "위도와 경도를 함께 입력해 주세요.")
        if self.place is None and not data.get("suggested_name"):
            self.add_error("suggested_name", "장소 이름을 입력해 주세요.")
        if self.place is None:
            has_point = data.get("lat") is not None and data.get("lng") is not None
            if not has_point and not data.get("location_text"):
                self.add_error("lat", "지도를 눌러 위치를 표시하거나, 위치 설명을 적어 주세요.")
        values = {k: data.get(k) for k in ENTRANCE_FIELDS}
        if all(v in (None, UNKNOWN) for v in values.values()) and not data.get("note"):
            raise forms.ValidationError("입구 정보를 하나 이상 고르거나, 추가 설명을 적어 주세요.")
        if self.place is not None and self.user is not None:
            since = timezone.now() - timedelta(hours=REPORT_LIMIT_HOURS)
            recent = Report.objects.filter(created_by=self.user, created_at__gte=since)
            if recent.filter(place=self.place).exists() or recent.filter(entrance__place=self.place).exists():
                raise forms.ValidationError("같은 장소는 24시간에 한 번만 제보할 수 있어요. 확인 중인 제보가 반영될 때까지 기다려 주세요.")
        return data

    def entrance_values(self):
        """{필드 키: 값} — '모름'과 빈 칸은 뺌"""
        out = {}
        for key in ENTRANCE_FIELDS:
            v = self.cleaned_data.get(key)
            if v in (None, UNKNOWN):
                continue
            out[key] = v
        return out
