from django.db import migrations


FIELDS = [
    ("entrance_available", "입구 이용 가능 여부", "ENTRANCE", "BOOL", "", []),
    ("entrance_automatic_door", "자동문", "ENTRANCE", "BOOL", "", []),
    ("facility_available", "시설 이용 가능 여부", "FACILITY", "BOOL", "", []),
    ("facility_connected_floors", "연결 층", "FACILITY", "TEXT", "", []),
    ("facility_wheelchair", "휠체어 이용 가능 여부", "FACILITY", "BOOL", "", []),
    ("facility_door_width_cm", "출입문 폭", "FACILITY", "NUMBER", "cm", []),
    ("facility_interior_space", "내부 공간", "FACILITY", "TEXT", "", []),
    ("facility_accessible_buttons", "접근 가능한 높이의 버튼", "FACILITY", "BOOL", "", []),
    ("facility_braille", "점자 안내", "FACILITY", "BOOL", "", []),
    ("facility_direction", "운행 방향", "FACILITY", "CHOICE", "", ["상승", "하강", "양방향"]),
    ("facility_operating", "운행 여부", "FACILITY", "BOOL", "", []),
    ("facility_alternative_route", "대체 경로", "FACILITY", "BOOL", "", []),
    ("facility_step_count", "계단 수", "FACILITY", "NUMBER", "칸", []),
    ("facility_handrail", "난간 / 손잡이", "FACILITY", "BOOL", "", []),
    ("facility_width_cm", "경사로 폭", "FACILITY", "NUMBER", "cm", []),
    ("facility_slope_deg", "경사 정도", "FACILITY", "NUMBER", "도", []),
]


def add_fields(apps, schema_editor):
    Field = apps.get_model("places", "FieldDefinition")
    for order, (key, label, scope, value_type, unit, choices) in enumerate(FIELDS, 100):
        Field.objects.using(schema_editor.connection.alias).get_or_create(
            key=key, defaults=dict(label=label, scope=scope, value_type=value_type,
                                  unit=unit, choices=choices, order=order, is_active=True),
        )


class Migration(migrations.Migration):
    dependencies = [("places", "0002_alter_fielddefinition_scope_accessfacility")]
    # 롤백 시 관측 이력이 참조하는 필드 정의를 지우지 않는다.
    operations = [migrations.RunPython(add_fields, migrations.RunPython.noop)]
