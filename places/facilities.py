"""시설별 관측 항목. 실제 값은 기존 FieldDefinition / AccessibilityValue에 저장한다."""

ENTRANCE = "ENTRANCE"
ENTRANCE_KEYS = (
    "step_height_cm", "step_count", "has_ramp", "door_width_cm", "door_type",
    "entrance_available", "entrance_automatic_door",
)

# key: (label, type, unit, choices, maximum). 수치는 모두 선택 입력이다.
FIELD_SPECS = {
    "entrance_available": ("입구 이용 가능 여부", "BOOL", "", [], None),
    "entrance_automatic_door": ("자동문", "BOOL", "", [], None),
    "facility_available": ("시설 이용 가능 여부", "BOOL", "", [], None),
    "facility_connected_floors": ("연결 층", "TEXT", "", [], None),
    "facility_wheelchair": ("휠체어 이용 가능 여부", "BOOL", "", [], None),
    "facility_door_width_cm": ("출입문 폭", "NUMBER", "cm", [], 1000),
    "facility_interior_space": ("내부 공간", "TEXT", "", [], None),
    "facility_accessible_buttons": ("접근 가능한 높이의 버튼", "BOOL", "", [], None),
    "facility_braille": ("점자 안내", "BOOL", "", [], None),
    "facility_direction": ("운행 방향", "CHOICE", "", ["상승", "하강", "양방향"], None),
    "facility_operating": ("운행 여부", "BOOL", "", [], None),
    "facility_alternative_route": ("대체 경로", "BOOL", "", [], None),
    "facility_step_count": ("계단 수", "NUMBER", "칸", [], 10000),
    "facility_handrail": ("난간 / 손잡이", "BOOL", "", [], None),
    "facility_width_cm": ("경사로 폭", "NUMBER", "cm", [], 1000),
    "facility_slope_deg": ("경사 정도", "NUMBER", "도", [], 90),
}

KIND_FIELDS = {
    ENTRANCE: ENTRANCE_KEYS,
    "ELEVATOR": ("facility_available", "facility_connected_floors", "facility_wheelchair",
                 "facility_door_width_cm", "facility_interior_space", "facility_accessible_buttons", "facility_braille"),
    "ESCALATOR": ("facility_available", "facility_connected_floors", "facility_direction",
                  "facility_operating", "facility_alternative_route"),
    "STAIRS": ("facility_available", "facility_connected_floors", "facility_step_count",
               "facility_handrail", "facility_alternative_route"),
    "RAMP": ("facility_available", "facility_width_cm", "facility_slope_deg", "facility_handrail"),
    "TOILET": ("facility_available", "facility_wheelchair", "facility_door_width_cm", "facility_handrail"),
    "OTHER": ("facility_available",),
}
