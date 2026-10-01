"""답사 CSV 가져오기 테스트 (F6)"""

import csv
import tempfile
from decimal import Decimal
from io import StringIO
from pathlib import Path

from django.core.management import CommandError, call_command
from django.test import TestCase
from PIL import Image

from judgments.models import Judgment
from places.models import Building, Place, Region
from reports.models import Report
from reports.selectors import current_values
from reports.test_views import TempMediaMixin

from .survey_import import SurveyError, import_survey, read_survey, template_rows

TEMPLATE = Path(__file__).resolve().parents[1] / "places" / "data" / "survey" / "template.csv"


class SurveyImportTests(TempMediaMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_base", stdout=StringIO())
        call_command("load_rules", stdout=StringIO())

    def setUp(self):
        self.use_temp_media()
        self.region = Region.objects.get(code="wolgye1")
        self.dir = Path(tempfile.mkdtemp())

    def write(self, *rows, encoding="utf-8-sig"):
        """양식 칸 이름으로 CSV를 만든다. rows: {칸 이름: 값}"""
        header = template_rows()[0]
        path = self.dir / "survey.csv"
        with open(path, "w", encoding=encoding, newline="") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            for row in rows:
                writer.writerow([row.get(h, "") for h in header])
        return path

    def row(self, **kw):
        base = {"이름": "턱없는 카페", "유형": "카페", "주소": "월계로 1", "위도": "37.6262", "경도": "127.0587",
                "확인일": "2026-09-20", "답사자": "강성훈",
                "입구 단차(cm)": "0", "계단 수(칸)": "0", "출입문 폭(cm)": "90", "고정 경사로": "없음"}
        return {**base, **kw}

    def judgment(self, name, profile="WHEELCHAIR"):
        return Judgment.objects.get(place__name=name, profile=profile).result

    def test_committed_template_matches_field_definitions(self):
        # 필드 정의를 바꾸면 양식도 다시 만들어야 함: python manage.py import_survey --template ...
        with open(TEMPLATE, encoding="utf-8-sig", newline="") as f:
            self.assertEqual(list(csv.reader(f)), template_rows())

    def test_import_creates_place_values_and_judgment(self):
        result = import_survey(self.write(self.row(), self.row(**{"이름": "계단 약국", "입구 단차(cm)": "15",
                                                                   "계단 수(칸)": "1", "유형": "약국"})))
        self.assertEqual(result.count("새 장소"), 2)
        cafe = Place.objects.get(name="턱없는 카페")
        self.assertEqual((cafe.category, cafe.lat, cafe.region), ("CAFE", Decimal("37.626200"), self.region))
        report = cafe.entrances.get().reports.get()
        self.assertEqual((report.source, report.status, report.note), ("TEAM_SURVEY", "VERIFIED", "답사: 강성훈"))
        self.assertEqual(report.observed_at.date().isoformat(), "2026-09-20")
        self.assertEqual(self.judgment("턱없는 카페"), "ACCESSIBLE")
        self.assertEqual(self.judgment("계단 약국"), "DIFFICULT")

    def test_reimport_is_idempotent_and_newer_survey_updates(self):
        path = self.write(self.row())
        import_survey(path)
        again = import_survey(path)
        self.assertEqual((again.count("변경 없음"), again.reports), (1, 0))
        self.assertEqual(Report.objects.count(), 1)
        # 다시 답사해서 값이 바뀌면 새 기록이 추가되고 판정이 바뀐다 (기존 기록은 이력으로 남음)
        import_survey(self.write(self.row(**{"확인일": "2026-09-25", "입구 단차(cm)": "15", "계단 수(칸)": "1"})))
        self.assertEqual(Report.objects.count(), 2)
        self.assertEqual(self.judgment("턱없는 카페"), "DIFFICULT")

    def test_blank_or_unknown_cells_do_not_overwrite(self):
        import_survey(self.write(self.row(**{"장애인 화장실": "있음"})))
        import_survey(self.write(self.row(**{"확인일": "2026-09-25", "장애인 화장실": "모름", "출입문 폭(cm)": ""})))
        cafe = Place.objects.get(name="턱없는 카페")
        self.assertIs(current_values(cafe)["accessible_toilet"].value, True)
        self.assertEqual(current_values(cafe.entrances.get())["door_width_cm"].value, Decimal("90"))

    def test_all_errors_reported_and_nothing_saved(self):
        path = self.write(
            self.row(),
            self.row(**{"이름": "", "위도": "127.05", "경도": "37.62"}),
            self.row(**{"이름": "잘못된 가게", "고정 경사로": "아마도", "출입문 형태": "유리문", "확인일": ""}),
        )
        with self.assertRaises(SurveyError) as ctx:
            import_survey(path)
        text = "\n".join(ctx.exception.errors)
        for expected in ("3번째 줄: 이름이 비어 있어요", "3번째 줄: 위도: 범위를 벗어났어요",
                         "4번째 줄: 고정 경사로: '있음' 또는 '없음'", "4번째 줄: 출입문 형태", "4번째 줄: 확인일이 비어"):
            self.assertIn(expected, text)
        self.assertFalse(Place.objects.exists())

    def test_unknown_column_rejected(self):
        path = self.dir / "bad.csv"
        path.write_text("이름,입구턱\n가게,3\n", encoding="utf-8")
        with self.assertRaisesMessage(SurveyError, "알 수 없는 칸: 입구턱"):
            read_survey(path)

    def test_excel_cp949_and_example_row_skipped(self):
        example = dict(zip(template_rows()[0], template_rows()[1]))
        import_survey(self.write(example, self.row(), encoding="cp949"))
        self.assertEqual(list(Place.objects.values_list("name", flat=True)), ["턱없는 카페"])

    def test_upper_floor_uses_building_entrance(self):
        import_survey(self.write(self.row(**{
            "이름": "2층 치과", "층": "2", "건물 이름": "월계빌딩", "건물 주소": "월계로 2",
            "건물 입구 단차(cm)": "20", "건물 계단 수(칸)": "2", "건물 출입문 폭(cm)": "100", "건물 고정 경사로": "없음",
            "엘리베이터": "없음",
        })))
        place = Place.objects.get(name="2층 치과")
        self.assertEqual(place.building, Building.objects.get(name="월계빌딩"))
        self.assertEqual(current_values(place.building)["elevator"].value, False)
        self.assertEqual(self.judgment("2층 치과"), "DIFFICULT")          # 가게 입구는 턱 없음, 건물 입구 계단 2칸

    def test_missing_coordinates_use_geocoder_for_new_place(self):
        path = self.write(self.row(**{"위도": "", "경도": ""}))
        import_survey(path, geocode=lambda query, near=None: (Decimal("37.600001"), Decimal("127.050001")))
        self.assertEqual(Place.objects.get().lat, Decimal("37.600001"))

        def fail(query, near=None):
            raise ValueError("주소를 찾지 못했어요")
        with self.assertRaisesMessage(SurveyError, "2번째 줄: 주소를 찾지 못했어요"):
            import_survey(self.write(self.row(**{"이름": "새 가게", "위도": "", "경도": ""})), geocode=fail)

    def test_photo_is_resized_and_attached(self):
        Image.new("RGB", (3200, 2400), "gray").save(self.dir / "door.jpg")
        import_survey(self.write(self.row(**{"입구 사진": "door.jpg"})), photos_dir=self.dir)
        photo = Place.objects.get().entrances.get().reports.get().photo
        with Image.open(photo) as im:
            self.assertEqual(max(im.size), 1600)
        with self.assertRaisesMessage(SurveyError, "입구 사진: 파일이 없어요"):
            read_survey(self.write(self.row(**{"입구 사진": "none.jpg"})), photos_dir=self.dir)

    def test_dry_run_saves_nothing_but_shows_judgments(self):
        result = import_survey(self.write(self.row()), dry_run=True)
        self.assertEqual(result.rows[0]["judgments"][0][1], "들어갈 수 있어요")
        self.assertFalse(Place.objects.exists())

    def test_command_output_and_error_exit(self):
        out = StringIO()
        call_command("import_survey", str(self.write(self.row())), stdout=out)
        self.assertIn("새 장소 1곳", out.getvalue())
        with self.assertRaisesMessage(CommandError, "고칠 곳이 1개"):
            call_command("import_survey", str(self.write(self.row(**{"확인일": "어제"}))), stdout=StringIO(),
                         stderr=StringIO())
