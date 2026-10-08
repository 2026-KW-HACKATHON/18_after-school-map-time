"""운영자 화면 폼 (와이어프레임 12·16·17번)"""

from django import forms
from django.db.models import Q
from django.utils import timezone

from judgments.models import ConditionProfile
from places.facilities import active_keys
from places.models import Place
from places.validation import numeric_form_options

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

    step_height_cm = forms.DecimalField(label="입구 단차 (cm)", required=False, **numeric_form_options("step_height_cm"), decimal_places=1)
    step_count = forms.IntegerField(label="계단 수 (칸)", required=False, **numeric_form_options("step_count"))
    has_ramp = forms.ChoiceField(label="고정 경사로", required=False, choices=BOOL_CHOICES)
    door_width_cm = forms.DecimalField(label="출입문 폭 (cm)", required=False, **numeric_form_options("door_width_cm"), decimal_places=1)
    door_type = forms.ChoiceField(label="출입문 형태", required=False)
    profiles = forms.MultipleChoiceField(label="이동 조건 (선택)", required=False,
                                        widget=forms.CheckboxSelectMultiple)
    interior_step = forms.ChoiceField(label="가게 안 단차", required=False, choices=BOOL_CHOICES)
    accessible_toilet = forms.ChoiceField(label="장애인 화장실", required=False, choices=BOOL_CHOICES)
    assistance_offered = forms.ChoiceField(label="입장 도움", required=False, choices=BOOL_CHOICES)
    portable_ramp = forms.ChoiceField(label="이동식 경사로", required=False, choices=BOOL_CHOICES)
    portable_ramp_length_cm = forms.DecimalField(label="이동식 경사로 길이 (cm)", required=False, **numeric_form_options("portable_ramp_length_cm"))

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
        # 기존 선택이 비활성화돼도 다른 정보를 저장하면서 잃지 않도록 표시한다.
        profiles = ConditionProfile.objects.filter(Q(is_active=True) | Q(key__in=self.initial.get("profiles", [])))
        self.fields["profiles"].choices = [
            (p.key, p.label if p.is_active else f"{p.label} (사용 중지)") for p in profiles
        ]
        if not self.instance.pk:
            self.fields["observed_on"].initial = timezone.localdate()
        # 관리자가 끄거나 지운 접근성 항목은 잠그고 저장하지 않는다 (주민 제보 폼과 같은 기준)
        self.active_keys = set(active_keys(ENTRANCE_KEYS + PLACE_KEYS))
        for key in ENTRANCE_KEYS + PLACE_KEYS:
            if key not in self.active_keys:
                self.fields[key].disabled = True
                self.fields[key].label += " (사용 중지)"

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
            if key not in self.active_keys:
                continue
            v = self.cleaned_data.get(key)
            if v in (None, UNKNOWN):
                continue
            out[key] = v
        return out


class PlaceDeleteForm(forms.Form):
    confirm = forms.BooleanField(label="장소와 연결된 기록을 영구 삭제하는 데 동의합니다.",
                                 error_messages={"required": "삭제할 내용을 확인하고 동의해 주세요."})


class ReportDeleteForm(forms.Form):
    """제보 기록 삭제 확인 — 되돌릴 수 없어서 동의 체크를 받는다"""

    confirm = forms.BooleanField(label="선택한 제보 기록과 사진을 영구 삭제하는 데 동의합니다.",
                                 error_messages={"required": "삭제할 내용을 확인하고 동의해 주세요."})


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
    address = forms.CharField(label="주소", max_length=200, required=False)
    floor = forms.IntegerField(label="층", required=False, min_value=-32768, max_value=32767,
                               help_text="1 = 1층, -1 = 지하 1층")
    phone = forms.CharField(label="전화번호", max_length=20, required=False)
    lat = forms.DecimalField(label="위도", max_digits=9, decimal_places=6, required=False, min_value=-90, max_value=90)
    lng = forms.DecimalField(label="경도", max_digits=9, decimal_places=6, required=False, min_value=-180, max_value=180)
    # 사진 수정·교체 요청을 승인할 때: 지금 공개된 입구 사진을 내림 (얼굴·번호판, 기획 v2 4.4)
    remove_current_photo = forms.BooleanField(label="지금 공개된 입구 사진 내리기 (얼굴·번호판·개인 정보가 보이면)", required=False)

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


# ── 운영자 AI 검토 보조 (reports/ai.py, AI 명세 v1.2 A안) ──
PRIVACY_CHECK_LABEL = "사진과 설명에 얼굴·차량 번호판·이름 등 개인정보가 남아 있지 않음을 확인했어요"


class AIAnalyzeForm(forms.Form):
    """'AI 후보 불러오기' — 보내기 전 운영자의 개인정보 점검 기록 (주민 동의를 대신하지 않음)"""

    privacy_checked = forms.BooleanField(label=PRIVACY_CHECK_LABEL,
                                         error_messages={"required": "보내기 전에 개인정보 확인에 체크해 주세요."})


class AISelectionForm(forms.Form):
    """
    AI 후보 중 운영자가 고른 항목만 저장. 모든 후보는 처음엔 선택 해제 (명세 9장).
    선택 체크박스와 값 칸을 나눈다 → 예/아니오는 있음·없음·모름 중 직접 고르고, 체크 안 한 칸을 false로 보지 않는다.
    """

    analysis_id = forms.UUIDField(widget=forms.HiddenInput)
    privacy_checked = forms.BooleanField(label=PRIVACY_CHECK_LABEL,
                                         error_messages={"required": "저장하기 전에 개인정보 확인에 체크해 주세요."})
    selected_keys = forms.MultipleChoiceField(label="저장할 항목", widget=forms.CheckboxSelectMultiple,
                                              error_messages={"required": "저장할 항목을 하나 이상 골라 주세요."})

    def __init__(self, *args, analysis, definitions, report_values=None, labels=None, all_keys=None, **kwargs):
        from places.models import FieldDefinition
        from places.validation import INTEGER_KEYS
        from reports.ai import AUTOMATIC_DOOR, CERTAINTY, ENTRANCE_KEYS, EVIDENCE_SOURCES, needs_text

        super().__init__(*args, **kwargs)
        # 분석할 때와 지금 모두 켜져 있는 항목만 고를 수 있음. 나머지는 표에 '분석 제외'로 (출입구 7개 고정)
        analysed = set(analysis.field_definition_snapshot or {})
        definitions = [f for f in definitions if f.key in analysed]
        self.definitions = definitions
        self.fields["selected_keys"].choices = [(f.key, f.label) for f in definitions]
        self.initial["analysis_id"] = analysis.pk
        candidates = (analysis.result or {}).get("fields", {})
        report_values = report_values or {}
        vt = FieldDefinition.ValueType
        rows = {}
        for f in definitions:
            name = f"value_{f.key}"
            if f.value_type == vt.NUMBER:
                if f.key in INTEGER_KEYS:
                    field = forms.IntegerField(required=False, **numeric_form_options(f.key))
                else:
                    field = forms.DecimalField(required=False, decimal_places=1, **numeric_form_options(f.key))
            elif f.value_type == vt.BOOL:
                field = forms.ChoiceField(required=False, choices=BOOL_CHOICES)
            elif f.value_type == vt.TEXT:
                field = forms.CharField(required=False, max_length=200)
            else:
                field = forms.ChoiceField(required=False, choices=[(UNKNOWN, "모름")] + [
                    (c, c) for c in f.choices if c != AUTOMATIC_DOOR])
            field.label = f"{f.label} 저장할 값"
            self.fields[name] = field
            candidate = candidates.get(f.key, {})
            value = candidate.get("value")
            if value is not None:
                self.initial[name] = ("true" if value else "false") if isinstance(value, bool) else value
            current = report_values.get(f.key)
            rows[f.key] = ({
                "key": f.key, "label": f.label, "unit": f.unit,
                "current": current.display_value if current else "",
                "candidate": "" if value is None else (("있음" if value else "없음") if isinstance(value, bool) else value),
                "certainty": CERTAINTY.get(candidate.get("certainty"), ""),
                "source": EVIDENCE_SOURCES.get(candidate.get("evidence_source"), ""),
                "evidence": candidate.get("evidence", ""),
                "needs_text": value is None and needs_text(f),  # 사진만으로는 알 수 없는 항목 → '모름' 대신 '설명 필요'
                "field": self[name],
            })
        labels = labels or {}
        self.rows = [rows.get(key) or {"key": key, "label": labels.get(key, key), "excluded": True}
                     for key in (all_keys or ENTRANCE_KEYS)]  # 제보 종류의 항목 전체 고정 (꺼진 항목은 '분석 제외')

    def clean(self):
        data = super().clean()
        for key in data.get("selected_keys", []):
            if data.get(f"value_{key}") in (None, UNKNOWN):
                self.add_error(f"value_{key}", "값을 고르거나 이 항목 선택을 풀어 주세요.")
        return data

    def selections(self):
        """{필드 키: 저장할 값} — 예/아니오는 bool로"""
        out = {}
        for key in self.cleaned_data["selected_keys"]:
            value = self.cleaned_data[f"value_{key}"]
            out[key] = {"true": True, "false": False}.get(value, value) if isinstance(value, str) else value
        return out
