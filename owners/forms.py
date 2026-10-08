from django import forms
from django.core.exceptions import ValidationError

from core.uploads import KeepPhotoMixin

from places.models import FieldDefinition
from reports.models import AccessibilityValue

from .models import OwnerResponse
from .services import PHOTO_REASONS

YES_NO = [("", "선택 안 함"), ("true", "있음"), ("false", "없음")]


class ClaimForm(forms.Form):
    code = forms.RegexField(
        label="인증 코드 (6자리 숫자)", regex=r"^\s*\d{6}\s*$",
        error_messages={"invalid": "6자리 숫자를 입력해 주세요."},
        widget=forms.TextInput(attrs={"inputmode": "numeric", "autocomplete": "one-time-code", "placeholder": "예: 123456"}),
    )


class ResponseForm(forms.ModelForm):
    """사장님 한마디·도움 요청 방법 (안내용이라 바로 공개)"""

    class Meta:
        model = OwnerResponse
        fields = ["owner_comment", "assistance_contact", "assistance_hours", "alt_entrance"]
        widgets = {"owner_comment": forms.Textarea(attrs={"rows": 3})}


class DeclarationForm(KeepPhotoMixin, forms.Form):
    """
    도움 제공 선언 (기획 v2 4.2). 사진 확인(주민 1명 또는 운영자)을 거쳐야 판정에 반영된다.
    """

    assistance_offered = forms.ChoiceField(label="직원이 입장을 도와드려요", choices=YES_NO, required=False)
    portable_ramp = forms.ChoiceField(label="이동식 경사로가 있어요", choices=YES_NO, required=False)
    portable_ramp_length_cm = forms.DecimalField(label="이동식 경사로 길이 (cm)", required=False, min_value=10, max_value=1000)
    photo = forms.ImageField(label="확인 사진", help_text="경사로를 펼친 모습이나 호출벨 등 선언한 내용이 보이는 사진")
    note = forms.CharField(label="덧붙일 말 (선택)", max_length=200, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_kept_photo()  # 오류로 다시 보여 줄 때 올린 사진 유지

    def clean(self):
        data = super().clean()
        if not data.get("assistance_offered") and not data.get("portable_ramp"):
            raise ValidationError("알려주실 항목을 하나 이상 골라 주세요.")
        if data.get("portable_ramp") == "true" and not data.get("portable_ramp_length_cm"):
            self.add_error("portable_ramp_length_cm", "경사로 길이를 적어 주세요. 오를 수 있는 턱 높이(길이 ÷ 8)를 계산하는 데 써요.")
        return data

    def values(self):
        out = {}
        for key in ("assistance_offered", "portable_ramp"):
            if self.cleaned_data.get(key):
                out[key] = self.cleaned_data[key]
        if self.cleaned_data.get("portable_ramp") == "true":
            out["portable_ramp_length_cm"] = self.cleaned_data["portable_ramp_length_cm"]
        return out


class CorrectionForm(KeepPhotoMixin, forms.Form):
    """정정 요청 (기획 v2 4.3): 항목 하나 + 새 값 + 증빙 사진. 다른 주민 2명 확인 또는 운영자 승인 후 반영"""

    field = forms.ChoiceField(label="고칠 항목")
    value = forms.CharField(label="올바른 값", max_length=50, help_text="숫자는 cm·칸 없이 숫자만, 있음/없음 항목은 '있음' 또는 '없음'")
    photo = forms.ImageField(label="증빙 사진")
    note = forms.CharField(label="이유 (선택)", max_length=200, required=False, widget=forms.Textarea(attrs={"rows": 2}))

    # 고칠 수 있는 항목의 대상과 화면 이름. 가게 사장님: 입구·가게 안 / 건물주: 건물 입구·건물 공용
    PLACE_SCOPES = {FieldDefinition.Scope.ENTRANCE: "입구", FieldDefinition.Scope.PLACE: "가게 안"}
    BUILDING_SCOPES = {FieldDefinition.Scope.ENTRANCE: "건물 입구", FieldDefinition.Scope.BUILDING: "건물 공용"}

    def __init__(self, *args, scopes=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_kept_photo()
        scopes = scopes or self.PLACE_SCOPES
        fields = FieldDefinition.objects.filter(scope__in=scopes, is_active=True).order_by("scope", "order")
        self.definitions = {f.key: f for f in fields}
        self.fields["field"].choices = [
            (f.key, f"{scopes[f.scope]} · {f.label}" + (f" ({'/'.join(f.choices)})" if f.choices else ""))
            for f in fields
        ]

    def clean(self):
        data = super().clean()
        definition = self.definitions.get(data.get("field"))
        if definition is None or not data.get("value"):
            return data
        raw = data["value"].strip()
        if definition.value_type == FieldDefinition.ValueType.BOOL and raw not in ("있음", "없음"):
            self.add_error("value", "'있음' 또는 '없음'으로 적어 주세요.")
            return data
        probe = AccessibilityValue(field=definition)
        try:
            probe.set_value(raw)
            probe.clean()
        except ValidationError as e:
            self.add_error("value", e.messages[0])
            return data
        data["definition"] = definition
        data["parsed"] = probe.value
        return data


class PhotoRequestForm(KeepPhotoMixin, forms.Form):
    """입구 사진 교체 요청 (기획 v2 4.4). 운영자가 얼굴·번호판을 확인하고 바꾼다. 정보 삭제 요청은 받지 않음"""

    reason = forms.ChoiceField(label="바꾸고 싶은 이유", choices=PHOTO_REASONS, widget=forms.RadioSelect)
    photo = forms.ImageField(label="새 입구 사진", help_text="입구 정면, 문턱·계단이 보이게. 사람 얼굴·차량 번호판은 나오지 않게 찍어 주세요")
    note = forms.CharField(label="덧붙일 말 (선택)", max_length=200, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_kept_photo()  # 오류로 다시 보여 줄 때 올린 사진 유지
