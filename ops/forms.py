"""운영자 화면 폼 (와이어프레임 12·16·17번)"""

from django import forms
from django.utils import timezone

from places.models import Place

UNKNOWN = ""
BOOL_CHOICES = [(UNKNOWN, "모름"), ("true", "있음"), ("false", "없음")]

# 운영자 장소 등록에서 받는 접근성 값 (필드 키 → 폼 칸). 입구 값은 주 출입구, 나머지는 장소에 저장
ENTRANCE_KEYS = ["step_height_cm", "step_count", "has_ramp", "door_width_cm", "door_type"]
PLACE_KEYS = ["interior_step", "accessible_toilet", "assistance_offered", "portable_ramp", "portable_ramp_length_cm"]


class PlaceForm(forms.ModelForm):
    """
    장소 등록·수정 (12번). 필수: 이름·위치(지도에서 선택). 접근성 값은 '팀 답사' 제보로 바로 반영된다.
    값을 비워 두면(모름) 기존 값을 건드리지 않는다.
    """

    step_height_cm = forms.DecimalField(label="입구 단차 (cm)", required=False, min_value=0, max_value=500, decimal_places=1)
    step_count = forms.IntegerField(label="계단 수 (칸)", required=False, min_value=0, max_value=50)
    has_ramp = forms.ChoiceField(label="고정 경사로", required=False, choices=BOOL_CHOICES)
    door_width_cm = forms.DecimalField(label="출입문 폭 (cm)", required=False, min_value=0, max_value=1000, decimal_places=1)
    door_type = forms.ChoiceField(label="출입문 형태", required=False)
    interior_step = forms.ChoiceField(label="가게 안 단차", required=False, choices=BOOL_CHOICES)
    accessible_toilet = forms.ChoiceField(label="장애인 화장실", required=False, choices=BOOL_CHOICES)
    assistance_offered = forms.ChoiceField(label="입장 도움", required=False, choices=BOOL_CHOICES)
    portable_ramp = forms.ChoiceField(label="이동식 경사로", required=False, choices=BOOL_CHOICES)
    portable_ramp_length_cm = forms.DecimalField(label="이동식 경사로 길이 (cm)", required=False, min_value=0, max_value=1000)

    source_note = forms.CharField(label="답사·확인 출처", max_length=100, required=False,
                                  widget=forms.TextInput(attrs={"placeholder": "예: 운영팀 직접 답사"}))
    observed_on = forms.DateField(label="최근 확인일", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    memo = forms.CharField(label="추가 메모 (선택)", max_length=300, required=False, widget=forms.Textarea(attrs={"rows": 2}))

    class Meta:
        model = Place
        fields = ["name", "category", "address", "floor", "phone", "lat", "lng", "is_closed"]
        labels = {"name": "장소명", "lat": "위도", "lng": "경도"}
        widgets = {"lat": forms.NumberInput(attrs={"step": "0.000001"}), "lng": forms.NumberInput(attrs={"step": "0.000001"})}

    REQUIRED_LABELS = {"name": "장소명", "lat": "위치 (지도에서 선택)", "lng": "위치 (지도에서 선택)"}

    def __init__(self, *args, door_choices=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["door_type"].choices = [(UNKNOWN, "모름")] + [(c, c) for c in door_choices]
        if not self.instance.pk:
            self.fields["observed_on"].initial = timezone.localdate()

    def missing_required(self):
        """와이어프레임 13번 '필수 항목 누락' 안내용: 비어 있는 필수 항목 이름 (중복 제거)"""
        names = []
        for field, label in self.REQUIRED_LABELS.items():
            if field in self.errors and label not in names:
                names.append(label)
        return names

    def values_for(self, keys):
        out = {}
        for key in keys:
            v = self.cleaned_data.get(key)
            if v in (None, UNKNOWN):
                continue
            out[key] = v
        return out


class ReviewForm(forms.Form):
    """제보 승인·반려 (16·17번)"""

    ACTIONS = [("approve", "승인"), ("reject", "반려")]

    action = forms.ChoiceField(choices=ACTIONS, widget=forms.HiddenInput)
    review_note = forms.CharField(label="검토 의견", max_length=300, required=False,
                                  widget=forms.Textarea(attrs={"rows": 2, "placeholder": "예: 제보 내용 반영, 재조사 필요 등"}))
    reject_reason = forms.CharField(label="반려 사유 (제보자에게 전달)", max_length=200, required=False,
                                    widget=forms.Textarea(attrs={"rows": 2}))
    # 새 장소 제안을 승인할 때 만들 장소 정보
    place_name = forms.CharField(label="장소명", max_length=100, required=False)
    category = forms.ChoiceField(label="유형", choices=Place.Category.choices, required=False)
    lat = forms.DecimalField(label="위도", max_digits=9, decimal_places=6, required=False)
    lng = forms.DecimalField(label="경도", max_digits=9, decimal_places=6, required=False)

    def __init__(self, *args, report=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.report = report

    def clean(self):
        data = super().clean()
        if data.get("action") == "reject" and not data.get("reject_reason"):
            self.add_error("reject_reason", "반려 사유를 입력해 주세요. 제보자에게 전달됩니다.")
        if data.get("action") == "approve" and self.report is not None and self.report.is_new_place:
            for key, msg in (("place_name", "장소명을 입력해 주세요."), ("lat", "위치를 지도에서 선택해 주세요."),
                             ("lng", "위치를 지도에서 선택해 주세요.")):
                if data.get(key) in (None, ""):
                    self.add_error(key, msg)
        return data
