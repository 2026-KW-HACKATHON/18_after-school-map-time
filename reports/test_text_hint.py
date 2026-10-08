"""사진만으로는 알 수 없는 항목을 '설명 필요'로 안내 (reports/ai.py TEXT_ONLY_KEYS)"""

from unittest import mock

from django.urls import reverse

from places.models import FieldDefinition

from . import ai
from .forms import ReportForm
from .test_ai import AIBase, FakeClient, body, clear, jpeg_upload, output


class NeedsTextTests(AIBase):
    def test_text_only_fields(self):
        defs = {f.key: f for f in FieldDefinition.objects.all()}
        for key in ("step_height_cm", "door_width_cm", "entrance_available", "facility_available",
                    "facility_connected_floors", "facility_interior_space", "facility_slope_deg",
                    "facility_door_width_cm", "facility_width_cm"):
            with self.subTest(key=key):
                self.assertTrue(ai.needs_text(defs[key]))
        # 사진으로 볼 수 있는 항목 (계단 칸 수·경사로·문 형태·난간)
        for key in ("step_count", "has_ramp", "door_type", "entrance_automatic_door",
                    "facility_step_count", "facility_handrail"):
            with self.subTest(key=key):
                self.assertFalse(ai.needs_text(defs[key]))

    def test_text_needed_lists_only_empty_text_only_fields(self):
        defs = ai.active_definitions()
        result = ai.validate_output(output(step_height_cm=clear(3)), defs)
        keys = [item["key"] for item in ai.text_needed(defs, result)]
        self.assertEqual(keys, ["door_width_cm", "entrance_available"])  # 단차는 설명에 있어 채워짐
        self.assertEqual(ai.text_needed(defs, result)[0]["label"], "출입문 폭")

    def test_note_field_explains_what_photo_cannot_show(self):
        note = ReportForm().fields["note"]
        self.assertIn("사진만으로는 알 수 없는 것", note.help_text)
        self.assertIn("재보니", note.widget.attrs["placeholder"])  # '약 3cm'처럼 쓰면 AI가 비우므로 잰 값 예시


class NeedsTextScreenTests(AIBase):
    def setUp(self):
        super().setUp()
        self.fake = FakeClient(body(output(step_count=clear(2, "계단 두 칸이 보임", "IMAGE"))))
        patcher = mock.patch("reports.ai.get_client", side_effect=lambda: self.fake)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_prefill_returns_fields_that_need_description(self):
        self.client.force_login(self.neighbor)
        data = self.client.post(reverse("reports:ai-prefill"),
                                {"facility_kind": "ENTRANCE", "note": "", "photo": jpeg_upload()}).json()
        self.assertTrue(data["ok"])
        self.assertEqual([i["key"] for i in data["needs_text"]], ["step_height_cm", "door_width_cm", "entrance_available"])

    def test_ops_review_marks_text_only_fields(self):
        self.client.force_login(self.staff)
        url = reverse("ops:report-review", args=[self.report.pk])
        self.client.post(url, {"action": "ai_analyze", "privacy_checked": "on"})
        page = self.client.get(url).content.decode()
        self.assertIn("설명 필요", page)
        self.assertIn("사진만으로는 알 수 없는 항목이에요", page)
        self.assertIn("모름", page)  # 사진으로 볼 수 있는데 비어 있는 항목(경사로 등)은 그대로 '모름'
