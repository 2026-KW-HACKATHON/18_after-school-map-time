"""
운영자 AI 검토 보조 (reports/ai.py, AI 명세 v1.2 A안).
모든 테스트는 가짜 OpenAI 클라이언트를 쓴다 → CI에 키·네트워크·결제가 필요 없다.
"""

import json
from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal
from io import StringIO
from unittest import mock

import requests
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.activity import my_reports
from accounts.models import User
from config.settings import _aware_datetime, _daily_limit
from judgments.services import required_confirmations
from places.models import Entrance, FieldDefinition
from places.selectors import place_detail
from places.tests import make_place, make_region

from . import ai
from .models import AccessibilityValue, AIAnalysis, Report, ReportConfirmation
from .services import ConfirmationError, confirm_report, verify_report
from .test_views import TempMediaMixin, photo

KEYS = list(ai.ENTRANCE_KEYS)
PAST = datetime(2026, 1, 1, tzinfo=dt_timezone.utc)
AI_ON = dict(AI_ENABLED=True, AI_PROVIDER="openai", OPENAI_API_KEY="test-key", OPENAI_MODEL="test-model",
             GEMINI_API_KEY="gemini-test-key", GEMINI_MODEL="gemini-3-flash-preview", GEMINI_THINKING_LEVEL="low",
             AI_DAILY_LIMIT=100,
             AI_NOTICE_SINCE=PAST, AI_NOTICE_VERSION="notice-test-1")


def unknown():
    return {"value": None, "evidence_source": "NONE", "evidence": "", "certainty": "UNKNOWN", "needs_manual_check": True}


def clear(value, evidence="설명에 적혀 있음", source="TEXT"):
    return {"value": value, "evidence_source": source, "evidence": evidence, "certainty": "CLEAR", "needs_manual_check": True}


def output(keys=KEYS, report_type="ACCESSIBILITY_OBSERVATION", warnings=(), **fields):
    data = {k: unknown() for k in keys}
    data.update(fields)
    return {"report_type": report_type, "summary": "설명에 단차 3cm와 경사로 없음이 적혀 있어요.",
            "fields": data, "warnings": list(warnings), "manual_check_items": []}


def body(data, status="completed", text=None):
    return {"id": "resp_test", "status": status, "usage": {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
            "output": [{"type": "message", "content": [
                {"type": "output_text", "text": text if text is not None else json.dumps(data, ensure_ascii=False)}]}]}


class FakeClient:
    def __init__(self, response=None, error=None, on_call=None):
        self.response, self.error, self.on_call, self.calls = response, error, on_call, []

    def create(self, request):
        """공통 요청을 받아 OpenAI 응답 모양을 해석해 돌려줌 (실제 클라이언트와 같은 반환 모양)"""
        self.calls.append(request)
        if self.on_call:
            self.on_call()
        if self.error:
            raise self.error
        return ai.parse_response(self.response)


def good():
    return FakeClient(body(output(step_height_cm=clear(3, "턱을 재보니 3cm"), has_ramp=clear(False, "경사로 없음"))))


@override_settings(**AI_ON)
class AIBase(TempMediaMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_base", stdout=StringIO())
        call_command("load_rules", stdout=StringIO())

    def setUp(self):
        self.use_temp_media()
        self.place = make_place(make_region("ai"), "월계 약국")
        self.entrance = Entrance.objects.create(place=self.place, name="정문", is_main=True)
        self.resident = User.objects.create_user(username="resident", date_joined=timezone.now() - timedelta(days=30))
        self.neighbor = User.objects.create_user(username="neighbor", date_joined=timezone.now() - timedelta(days=30))
        self.staff = User.objects.create_user(username="staff", is_staff=True)
        self.report = self.make_report()

    def make_report(self, **kwargs):
        fields = dict(source=Report.Source.USER_REPORT, status=Report.Status.PENDING, entrance=self.entrance,
                      created_by=self.resident, note="입구 턱 재보니 3cm. 사장님 번호는 010-1234-5678로 연락", photo=photo(),
                      ai_notice_version="notice-test-1")
        fields.update(kwargs)
        report = Report.objects.create(**fields)
        if report.target_scope == FieldDefinition.Scope.ENTRANCE:
            value = AccessibilityValue(report=report, field_id="step_height_cm")
            value.set_value("5")
            value.save()
        return report

    def values(self, report=None):
        return {v.field_id: v.value for v in (report or self.report).values.select_related("field")}


class MaskAndSettingsTests(TestCase):
    def test_phone_numbers_are_masked_even_with_korean_particles(self):
        for text in ("010-1234-5678로 연락", "번호는 010-1234-5678입니다", "전화01012345678", "(02)123-4567",
                     "+82-10-1234-5678", "1588-1234", "０１０－１２３４－５６７８", "031 123 4567"):
            with self.subTest(text=text):
                masked = ai.mask_phone(text)
                self.assertIn("[전화번호]", masked)
                self.assertNotRegex(masked, r"\d{4}")

    def test_measurements_and_dates_are_kept(self):
        for text in ("단차 3cm", "문 폭 90cm", "0.9m", "2026-10-04 확인", "1600 1200 크기"):
            with self.subTest(text=text):
                self.assertEqual(ai.mask_phone(text), text)

    def test_settings_parsers_never_mean_unlimited(self):
        self.assertEqual([_daily_limit(v) for v in ("100", "0", "-3", "abc", None)], [100, 0, 0, 0, 0])
        self.assertEqual(_aware_datetime("2026-10-07T00:00:00+09:00").utcoffset(), timedelta(hours=9))
        self.assertIsNone(_aware_datetime("2026-10-07T00:00:00"))  # 시간대 없으면 받지 않음
        self.assertIsNone(_aware_datetime(""))


class AnalyzeTests(AIBase):
    def test_success_stores_candidates_without_touching_report(self):
        client = good()
        analysis, reused = ai.analyze(self.report, self.staff, client=client)
        self.assertFalse(reused)
        self.assertEqual(analysis.status, AIAnalysis.Status.SUCCEEDED)
        self.assertEqual(analysis.result["fields"]["step_height_cm"]["value"], 3)
        self.assertIs(analysis.result["fields"]["has_ramp"]["value"], False)
        self.assertEqual(analysis.usage["total_tokens"], 120)
        self.assertEqual(analysis.provider_response_id, "resp_test")
        # 분석만으로는 제보·값·주민 확인 정책이 바뀌지 않음
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, Report.Status.PENDING)
        self.assertEqual(self.values(), {"step_height_cm": Decimal("5.00")})
        self.assertFalse(ai.staff_review_only(self.report))
        self.assertIsNotNone(required_confirmations(self.report))

    def test_payload_sends_masked_note_photo_and_strict_schema_only(self):
        client = good()
        ai.analyze(self.report, self.staff, client=client)
        payload = ai.OpenAIClient().payload(client.calls[0])
        sent = json.dumps(client.calls[0], ensure_ascii=False)
        self.assertNotIn("010-1234-5678", sent)
        self.assertIn("[전화번호]", sent)
        self.assertNotIn(self.resident.username, sent)  # 계정은 보내지 않음
        self.assertIs(payload["store"], False)
        self.assertEqual(payload["model"], "test-model")
        content = payload["input"][0]["content"]
        self.assertTrue(content[1]["image_url"].startswith("data:image/jpeg;base64,"))
        schema = payload["text"]["format"]["schema"]
        self.assertTrue(payload["text"]["format"]["strict"])
        self.assertEqual(schema["properties"]["fields"]["required"], KEYS)
        self.assertNotIn("자동문", schema["properties"]["fields"]["properties"]["door_type"]["properties"]["value"]["enum"])

    def test_same_input_reuses_result_without_another_call(self):
        client = good()
        first, _ = ai.analyze(self.report, self.staff, client=client)
        second, reused = ai.analyze(self.report, self.staff, client=client)
        self.assertTrue(reused)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(len(client.calls), 1)

    def test_inactive_field_is_left_out_of_schema(self):
        FieldDefinition.objects.filter(key="entrance_available").update(is_active=False)
        keys = [k for k in KEYS if k != "entrance_available"]
        client = FakeClient(body(output(keys=keys, step_height_cm=clear(3))))
        analysis, _ = ai.analyze(self.report, self.staff, client=client)
        self.assertNotIn("entrance_available", client.calls[0]["schema"]["properties"]["fields"]["properties"])
        self.assertEqual(set(analysis.result["fields"]), set(keys))

    def test_reports_that_are_not_for_ai_are_never_sent(self):
        client = good()
        cases = {
            "UNSUPPORTED_REPORT_TYPE": [self.make_report(source=Report.Source.OWNER),
                                        self.make_report(note="[사진 수정 요청] 예전 모습이에요")],
            "REPORT_NOT_PENDING": [self.make_report(status=Report.Status.VERIFIED)],
            "UNSUPPORTED_SCOPE": [self.make_report(entrance=None, place=self.place, facility_kind="ELEVATOR")],
        }
        for code, reports in cases.items():
            for report in reports:
                with self.subTest(code=code, report=report.pk), self.assertRaises(ai.AIError) as e:
                    ai.analyze(report, self.staff, client=client)
                self.assertEqual(e.exception.code, code)
        self.assertEqual(client.calls, [])
        self.assertFalse(AIAnalysis.objects.exists())

    def test_reports_before_notice_or_without_notice_time_are_not_sent(self):
        client = good()
        for since in (timezone.now() + timedelta(hours=1), None):
            with self.subTest(since=since), override_settings(AI_NOTICE_SINCE=since), self.assertRaises(ai.AIError) as e:
                ai.analyze(self.report, self.staff, client=client)
            self.assertEqual(e.exception.code, "NOTICE_NOT_APPLIED")
        self.assertEqual(client.calls, [])

    def test_disabled_or_unconfigured_ai_makes_no_call(self):
        client = good()
        for overrides, code in (({"AI_ENABLED": False}, "AI_DISABLED"), ({"OPENAI_API_KEY": ""}, "AI_UNAVAILABLE"),
                                ({"OPENAI_MODEL": ""}, "AI_UNAVAILABLE")):
            with self.subTest(code=code), override_settings(**overrides), self.assertRaises(ai.AIError) as e:
                ai.analyze(self.report, self.staff, client=client)
            self.assertEqual(e.exception.code, code)
        self.assertEqual(client.calls, [])

    def test_provider_failures_are_recorded_and_report_is_kept(self):
        refusal = {"id": "r", "status": "completed",
                   "output": [{"type": "message", "content": [{"type": "refusal", "refusal": "거절"}]}]}
        cases = {
            "AI_REFUSAL": FakeClient(refusal),
            "AI_INCOMPLETE": FakeClient(body(output(), status="incomplete")),
            "AI_INVALID_OUTPUT": FakeClient(body(None, text="JSON 아님")),
            "AI_TIMEOUT": FakeClient(error=ai.AIError("AI_TIMEOUT")),
            "INTERNAL_ERROR": FakeClient(error=RuntimeError("예상 못한 오류")),
        }
        missing = output()
        del missing["fields"]["door_type"]
        cases["AI_INVALID_OUTPUT "] = FakeClient(body(missing))  # 항목 누락
        wrong_type = output(step_count=clear("두 칸"))
        cases["AI_INVALID_OUTPUT  "] = FakeClient(body(wrong_type))  # 타입 오류
        for code, client in cases.items():
            # 예상한 오류 기록이 테스트 출력에 섞이지 않게 로거만 바꿔 둠
            with self.subTest(code=code.strip()), mock.patch("reports.ai.logger"):
                AIAnalysis.objects.all().delete()
                with self.assertRaises(ai.AIError) as e:
                    ai.analyze(self.report, self.staff, client=client)
                self.assertEqual(e.exception.code, code.strip())
                analysis = AIAnalysis.objects.get()
                self.assertEqual((analysis.status, analysis.error_code), (AIAnalysis.Status.FAILED, code.strip()))
                self.assertNotIn("예상 못한 오류", analysis.error_message)  # 원문 대신 정리한 안내만
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, Report.Status.PENDING)
        self.assertEqual(self.values(), {"step_height_cm": Decimal("5.00")})

    def test_out_of_range_or_uncertain_values_become_unknown_with_check_item(self):
        data = output(step_height_cm=clear(900), door_width_cm=clear(85.25), step_count=clear(2.5),
                      door_type={**clear("미닫이"), "certainty": "UNCERTAIN"})
        analysis, _ = ai.analyze(self.report, self.staff, client=FakeClient(body(data)))
        fields = analysis.result["fields"]
        for key in ("step_height_cm", "door_width_cm", "step_count", "door_type"):
            self.assertIsNone(fields[key]["value"], key)
            self.assertEqual(fields[key]["certainty"], "UNCERTAIN")
        self.assertEqual(len(analysis.result["manual_check_items"]), 3)

    def test_unrelated_content_gives_no_values(self):
        data = output(report_type="OTHER", has_ramp=clear(True))
        analysis, _ = ai.analyze(self.report, self.staff, client=FakeClient(body(data)))
        self.assertIsNone(analysis.result["fields"]["has_ramp"]["value"])

    def test_daily_limit_counts_failed_attempts(self):
        with override_settings(AI_DAILY_LIMIT=1):
            with self.assertRaises(ai.AIError):
                ai.analyze(self.report, self.staff, client=FakeClient(error=ai.AIError("AI_TIMEOUT")))
            client = good()
            with self.assertRaises(ai.AIError) as e:
                ai.analyze(self.report, self.staff, client=client)
        self.assertEqual(e.exception.code, "DAILY_LIMIT_REACHED")
        self.assertEqual(client.calls, [])
        with override_settings(AI_DAILY_LIMIT=0), self.assertRaises(ai.AIError):
            ai.analyze(self.make_report(), self.staff, client=good())

    def test_processing_blocks_for_60_seconds_then_counts_as_failed(self):
        stuck = AIAnalysis.objects.create(report=self.report, status=AIAnalysis.Status.PROCESSING)
        with self.assertRaises(ai.AIError) as e:
            ai.analyze(self.report, self.staff, client=good())
        self.assertEqual(e.exception.code, "ANALYSIS_IN_PROGRESS")
        AIAnalysis.objects.filter(pk=stuck.pk).update(created_at=timezone.now() - timedelta(seconds=61))
        stuck.refresh_from_db()
        self.assertEqual(ai.effective_status(stuck), AIAnalysis.Status.FAILED)
        analysis, _ = ai.analyze(self.report, self.staff, client=good())
        self.assertEqual(analysis.status, AIAnalysis.Status.SUCCEEDED)

    def test_report_changed_during_call_discards_old_candidates(self):
        def change():
            value = self.report.values.get(field_id="step_height_cm")
            value.set_value("7")
            value.save()
        with self.assertRaises(ai.AIError) as e:
            ai.analyze(self.report, self.staff, client=FakeClient(good().response, on_call=change))
        self.assertEqual(e.exception.code, "STALE_ANALYSIS")
        self.assertEqual(AIAnalysis.objects.get().status, AIAnalysis.Status.FAILED)


REQUEST = {"instructions": "지시문", "text": "주민 설명: 턱 3cm", "image": "QUJD", "schema": {"type": "object"},
           "max_output_tokens": 2500}


class OpenAIClientTests(TestCase):
    """실제 호출부: 네트워크 대신 requests.post를 바꿔 오류 분류만 확인"""

    def call(self, **post):
        with mock.patch("reports.ai.requests.post", **post), self.assertRaises(ai.AIError) as e:
            ai.OpenAIClient().create(REQUEST)
        return e.exception.code

    def response(self, status, payload):
        res = mock.Mock(status_code=status)
        res.json.return_value = payload
        return res

    def test_error_mapping(self):
        self.assertEqual(self.call(side_effect=requests.Timeout()), "AI_TIMEOUT")
        self.assertEqual(self.call(side_effect=requests.ConnectionError()), "AI_UNAVAILABLE")
        self.assertEqual(self.call(return_value=self.response(429, {"error": {"code": "insufficient_quota"}})),
                         "AI_BUDGET_EXCEEDED")
        self.assertEqual(self.call(return_value=self.response(429, {"error": {"code": "rate_limit_exceeded"}})),
                         "AI_UNAVAILABLE")
        self.assertEqual(self.call(return_value=self.response(401, {"error": {"code": "invalid_api_key"}})),
                         "AI_UNAVAILABLE")

    @override_settings(OPENAI_API_KEY="sk-test")
    def test_request_uses_timeout_and_server_key(self):
        with mock.patch("reports.ai.requests.post", return_value=self.response(200, body(output()))) as post:
            data, response_id, usage = ai.OpenAIClient().create(REQUEST)
        self.assertEqual((data["report_type"], response_id, usage["total_tokens"]), ("ACCESSIBILITY_OBSERVATION", "resp_test", 120))
        kwargs = post.call_args.kwargs
        self.assertEqual(kwargs["timeout"], ai.OPENAI_TIMEOUT)
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer sk-test")


class SelectionTests(AIBase):
    def setUp(self):
        super().setUp()
        self.analysis, _ = ai.analyze(self.report, self.staff, client=good())

    def test_only_selected_keys_are_saved_and_report_stays_pending(self):
        observed_at, source = self.report.observed_at, self.report.source
        changes = ai.save_selection(self.analysis, self.staff, {"step_height_cm": Decimal("3"), "has_ramp": False})
        self.assertEqual([c["key"] for c in changes], ["step_height_cm", "has_ramp"])
        self.assertEqual(changes[0], {"key": "step_height_cm", "before": "5", "after": "3"})
        self.report.refresh_from_db()
        self.assertEqual(self.values(), {"step_height_cm": Decimal("3.00"), "has_ramp": False})
        self.assertEqual((self.report.status, self.report.source, self.report.observed_at),
                         (Report.Status.PENDING, source, observed_at))
        self.analysis.refresh_from_db()
        self.assertEqual(self.analysis.selection_history[0]["by_name"], "staff")

    def test_selection_is_saved_once_per_analysis(self):
        ai.save_selection(self.analysis, self.staff, {"has_ramp": False})
        with self.assertRaises(ai.AIError) as e:
            ai.save_selection(self.analysis, self.staff, {"has_ramp": True})
        self.assertEqual(e.exception.code, "SELECTION_ALREADY_SAVED")
        self.assertIs(self.values()["has_ramp"], False)

    def test_changed_report_or_definitions_block_old_candidates(self):
        value = self.report.values.get(field_id="step_height_cm")
        value.set_value("9")
        value.save()
        with self.assertRaises(ai.AIError) as e:
            ai.save_selection(self.analysis, self.staff, {"has_ramp": False})
        self.assertEqual(e.exception.code, "STALE_ANALYSIS")
        self.assertNotIn("has_ramp", self.values())

        report = self.make_report()
        analysis, _ = ai.analyze(report, self.staff, client=good())
        FieldDefinition.objects.filter(key="entrance_available").update(is_active=False)
        with self.assertRaises(ai.AIError) as e:
            ai.save_selection(analysis, self.staff, {"has_ramp": False})
        self.assertEqual(e.exception.code, "STALE_ANALYSIS")

    def test_automatic_door_rules(self):
        with self.assertRaises(ai.AIError):
            ai.save_selection(self.analysis, self.staff, {"door_type": "자동문"})
        report = self.make_report()
        door = AccessibilityValue(report=report, field_id="door_type")
        door.set_value("자동문")
        door.save()
        analysis, _ = ai.analyze(report, self.staff, client=good())
        with self.assertRaises(ai.AIError) as e:
            ai.save_selection(analysis, self.staff, {"entrance_automatic_door": False})
        self.assertIn("자동문", e.exception.message)
        # 문 형태도 함께 고치면 저장 가능
        ai.save_selection(analysis, self.staff, {"entrance_automatic_door": False, "door_type": "여닫이"})
        self.assertEqual(self.values(report)["door_type"], "여닫이")

    def test_invalid_value_rolls_back_everything(self):
        with self.assertRaises(ai.AIError) as e:
            ai.save_selection(self.analysis, self.staff, {"step_height_cm": Decimal("3"), "door_width_cm": Decimal("5000")})
        self.assertEqual(e.exception.code, "INVALID_REQUEST")
        self.assertEqual(self.values(), {"step_height_cm": Decimal("5.00")})
        self.analysis.refresh_from_db()
        self.assertEqual(self.analysis.selection_history, [])
        for bad in ({}, {"unknown_key": 1}, {"has_ramp": None}):
            with self.subTest(bad=bad), self.assertRaises(ai.AIError):
                ai.save_selection(self.analysis, self.staff, bad)

    def test_processed_report_cannot_take_candidates(self):
        verify_report(self.report, by=self.staff)
        with self.assertRaises(ai.AIError) as e:
            ai.save_selection(self.analysis, self.staff, {"has_ramp": False})
        self.assertEqual(e.exception.code, "REPORT_NOT_PENDING")


class StaffOnlyAfterSelectionTests(AIBase):
    """AI 후보를 골라 저장한 제보: 이전 주민 확인은 쓰지 않고 운영자만 승인 (명세 6장)"""

    def setUp(self):
        super().setUp()
        ReportConfirmation.objects.create(report=self.report, user=self.neighbor)  # 고치기 전 값에 대한 확인
        analysis, _ = ai.analyze(self.report, self.staff, client=good())
        ai.save_selection(analysis, self.staff, {"has_ramp": False})

    def test_resident_confirmations_no_longer_apply(self):
        self.assertTrue(ai.staff_review_only(self.report))
        self.assertIsNone(required_confirmations(self.report))
        other = User.objects.create_user(username="other", date_joined=timezone.now() - timedelta(days=30))
        with self.assertRaises(ConfirmationError):
            confirm_report(self.report, other, required=1)  # 부르는 쪽이 옛 required를 넘겨도 거부
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, Report.Status.PENDING)

    def test_only_active_staff_can_approve(self):
        with self.assertRaises(PermissionDenied):
            verify_report(self.report, by=None)
        with self.assertRaises(PermissionDenied):
            verify_report(self.report, by=self.neighbor)
        verify_report(self.report, by=self.staff)
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, Report.Status.VERIFIED)

    def test_public_screens_do_not_offer_resident_confirmation(self):
        self.assertEqual(place_detail(self.place)["pending_reports"], [])
        row = next(r for r in my_reports(self.resident) if r["report"].pk == self.report.pk)
        self.assertIn("운영진", row["progress"])
        self.client.force_login(self.neighbor)
        self.client.post(reverse("reports:confirm", args=[self.report.pk]))
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, Report.Status.PENDING)


class OpsReviewScreenTests(AIBase):
    def setUp(self):
        super().setUp()
        self.url = reverse("ops:report-review", args=[self.report.pk])
        self.client.force_login(self.staff)
        patcher = mock.patch("reports.ai.get_client", side_effect=lambda: self.fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.fake = good()

    def test_non_staff_cannot_use_ai(self):
        self.client.force_login(self.resident)
        res = self.client.post(self.url, {"action": "ai_analyze", "privacy_checked": "on"})
        self.assertEqual(res.status_code, 302)
        self.assertIn(reverse("ops:login"), res["Location"])
        self.assertEqual(self.fake.calls, [])

    def test_analyze_needs_privacy_check(self):
        res = self.client.post(self.url, {"action": "ai_analyze"})
        self.assertRedirects(res, self.url + "#ai", fetch_redirect_response=False)
        self.assertEqual(self.fake.calls, [])

    def test_full_flow_analyze_pick_save_then_approve(self):
        page = self.client.get(self.url)
        self.assertContains(page, "OpenAI(미국)")
        self.assertContains(page, "[전화번호]")  # 보낼 설명 미리보기도 가린 상태
        self.assertNotContains(page, 'name="selected_keys"')

        self.client.post(self.url, {"action": "ai_analyze", "privacy_checked": "on"})
        self.assertEqual(len(self.fake.calls), 1)
        page = self.client.get(self.url)
        self.assertContains(page, 'name="selected_keys"')
        self.assertContains(page, "턱을 재보니 3cm")
        self.assertNotContains(page, 'name="selected_keys" value="step_height_cm" id="ai-pick-step_height_cm" aria-label="입구 단차 저장" checked')  # 처음엔 선택 해제
        analysis = AIAnalysis.objects.get()

        # 고른 칸에 값이 없으면 같은 화면에 오류, 아무것도 저장 안 됨
        res = self.client.post(self.url, {"action": "ai_save", "analysis_id": analysis.pk, "privacy_checked": "on",
                                          "selected_keys": ["door_width_cm"], "value_door_width_cm": ""})
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "값을 고르거나 이 항목 선택을 풀어 주세요.")
        self.assertNotIn("door_width_cm", self.values())

        res = self.client.post(self.url, {"action": "ai_save", "analysis_id": analysis.pk, "privacy_checked": "on",
                                          "selected_keys": ["step_height_cm", "has_ramp"],
                                          "value_step_height_cm": "3", "value_has_ramp": "false"})
        self.assertRedirects(res, self.url + "#ai", fetch_redirect_response=False)
        self.assertEqual(self.values(), {"step_height_cm": Decimal("3.00"), "has_ramp": False})
        page = self.client.get(self.url)
        self.assertContains(page, "운영자만 승인해요")
        self.assertContains(page, "입구 단차 5 → 3")

        res = self.client.post(self.url, {"action": "approve", "review_note": "AI 후보 확인"})
        self.assertRedirects(res, reverse("ops:report-done", args=[self.report.pk]), fetch_redirect_response=False)
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, Report.Status.VERIFIED)

    def test_failure_shows_manual_review_message(self):
        self.fake = FakeClient(error=ai.AIError("AI_TIMEOUT"))
        self.client.post(self.url, {"action": "ai_analyze", "privacy_checked": "on"})
        page = self.client.get(self.url)
        self.assertContains(page, "AI 분석을 완료하지 못했어요. 사진과 설명을 직접 검토해 주세요.")

    def test_unknown_analysis_id_is_404(self):
        res = self.client.post(self.url, {"action": "ai_save", "analysis_id": "not-a-uuid"})
        self.assertEqual(res.status_code, 404)

    @override_settings(AI_ENABLED=False)
    def test_section_hidden_when_ai_off(self):
        page = self.client.get(self.url)
        self.assertNotContains(page, "AI 검토 보조")
        self.client.post(self.url, {"action": "ai_analyze", "privacy_checked": "on"})
        self.assertEqual(self.fake.calls, [])


class ResidentNoticeTests(AIBase):
    def test_notice_only_when_ai_on(self):
        self.client.force_login(self.resident)
        url = reverse("reports:new") + f"?place={self.place.pk}"
        self.assertContains(self.client.get(url), "OpenAI(미국)")
        with override_settings(AI_ENABLED=False):
            self.assertNotContains(self.client.get(url), "OpenAI(미국)")


class SpecV13Tests(AIBase):
    """AI 명세 v1.3 추가 사항"""

    def test_duplicate_keys_and_non_finite_numbers_are_rejected(self):
        valid = json.dumps(output(), ensure_ascii=False)
        cases = {
            "최상위 중복": valid[:-1] + ', "summary": "두 번째"}',
            "항목 안 중복": valid.replace('"certainty": "UNKNOWN"', '"certainty": "UNKNOWN", "certainty": "CLEAR"', 1),
            "NaN": valid.replace('"value": null', '"value": NaN', 1),
        }
        for name, text in cases.items():
            with self.subTest(name=name), self.assertRaises(ai.AIError) as e:
                ai.strict_json(text)
            self.assertEqual(e.exception.code, "AI_INVALID_OUTPUT")
        self.assertEqual(ai.strict_json(valid)["report_type"], "ACCESSIBILITY_OBSERVATION")
        with mock.patch("reports.ai.logger"), self.assertRaises(ai.AIError):
            ai.analyze(self.report, self.staff, client=FakeClient(body(None, text=cases["항목 안 중복"])))
        self.assertEqual(AIAnalysis.objects.get().error_code, "AI_INVALID_OUTPUT")

    def test_notice_version_must_match(self):
        client = good()
        for version in ("", "notice-old"):
            report = self.make_report(ai_notice_version=version)
            with self.subTest(version=version), self.assertRaises(ai.AIError) as e:
                ai.analyze(report, self.staff, client=client)
            self.assertEqual(e.exception.code, "NOTICE_NOT_APPLIED")
        with override_settings(AI_NOTICE_VERSION=""), self.assertRaises(ai.AIError):
            ai.analyze(self.report, self.staff, client=client)
        self.assertEqual(client.calls, [])

    def test_notice_check_runs_before_reuse(self):
        ai.analyze(self.report, self.staff, client=good())
        with override_settings(AI_NOTICE_VERSION="notice-test-2"), self.assertRaises(ai.AIError) as e:
            ai.analyze(self.report, self.staff, client=good())
        self.assertEqual(e.exception.code, "NOTICE_NOT_APPLIED")

    def test_processing_59_seconds_is_running_60_seconds_is_timeout(self):
        stuck = AIAnalysis.objects.create(report=self.report, status=AIAnalysis.Status.PROCESSING)
        for seconds, status in ((59, AIAnalysis.Status.PROCESSING), (60, AIAnalysis.Status.FAILED)):
            AIAnalysis.objects.filter(pk=stuck.pk).update(created_at=timezone.now() - timedelta(seconds=seconds))
            stuck.refresh_from_db()
            with self.subTest(seconds=seconds):
                self.assertEqual(ai.effective_status(stuck), status)
        self.assertEqual(ai.effective_error(stuck)[0], "AI_TIMEOUT")

    def test_late_response_is_not_saved(self):
        def slow():  # 응답이 오기 전에 요청 시각이 26초 지난 것처럼
            AIAnalysis.objects.update(created_at=timezone.now() - timedelta(seconds=26))
        with self.assertRaises(ai.AIError) as e:
            ai.analyze(self.report, self.staff, client=FakeClient(good().response, on_call=slow))
        self.assertEqual(e.exception.code, "AI_TIMEOUT")
        analysis = AIAnalysis.objects.get()
        self.assertEqual((analysis.status, analysis.result), (AIAnalysis.Status.FAILED, None))

    def test_old_schema_result_is_not_reused_or_selectable(self):
        old, _ = ai.analyze(self.report, self.staff, client=good())
        AIAnalysis.objects.filter(pk=old.pk).update(schema_version="entrance-analysis-v2",
                                                    prompt_version="entrance-extract-v2")
        old.refresh_from_db()
        with self.assertRaises(ai.AIError) as e:
            ai.save_selection(old, self.staff, {"has_ramp": False})
        self.assertEqual(e.exception.code, "UNSUPPORTED_SCHEMA_VERSION")
        client = good()
        new, reused = ai.analyze(self.report, self.staff, client=client)
        self.assertFalse(reused)
        self.assertEqual((len(client.calls), new.schema_version), (1, ai.SCHEMA_VERSION))

    def test_deleting_report_keeps_daily_count_and_clears_content(self):
        analysis, _ = ai.analyze(self.report, self.staff, client=good())
        ai.save_selection(analysis, self.staff, {"has_ramp": False})
        before = ai.attempts_today()
        self.report.delete()
        analysis.refresh_from_db()
        self.assertIsNone(analysis.report_id)
        self.assertEqual((analysis.input_snapshot, analysis.result, analysis.selection_history, analysis.usage),
                         ({}, None, [], None))
        self.assertIsNone(analysis.requested_by_id)
        self.assertEqual(ai.attempts_today(), before)  # 지워도 오늘 횟수는 그대로

    def test_report_deleted_during_call_is_not_revived(self):
        with mock.patch("reports.ai.logger"), self.assertRaises(ai.AIError) as e:
            ai.analyze(self.report, self.staff, client=FakeClient(good().response, on_call=self.report.delete))
        self.assertEqual(e.exception.code, "REPORT_NOT_FOUND")
        analysis = AIAnalysis.objects.get()
        self.assertEqual((analysis.status, analysis.report_id, analysis.result, analysis.input_snapshot),
                         (AIAnalysis.Status.FAILED, None, None, {}))
        self.assertEqual(ai.attempts_today(), 1)

    def test_deleting_place_also_clears_ai_content(self):
        analysis, _ = ai.analyze(self.report, self.staff, client=good())
        self.place.delete()
        analysis.refresh_from_db()
        self.assertEqual((analysis.report_id, analysis.input_snapshot), (None, {}))

    def test_my_activity_and_badge_skip_confirmations_on_ai_edited_reports(self):
        from accounts.activity import badges, counts

        ReportConfirmation.objects.create(report=self.report, user=self.neighbor)
        other = self.make_report()
        ReportConfirmation.objects.create(report=other, user=self.neighbor)
        self.assertEqual(counts(self.neighbor)["confirmations"], 2)
        analysis, _ = ai.analyze(self.report, self.staff, client=good())
        ai.save_selection(analysis, self.staff, {"has_ramp": False})
        self.assertEqual(counts(self.neighbor)["confirmations"], 1)
        badge = next(b for b in badges(counts(self.neighbor)) if b["key"] == "neighbor_check")
        self.assertEqual(badge["progress"], "1/3")
        verify_report(self.report, by=self.staff)  # 승인한 뒤에도 되살리지 않음
        self.assertEqual(counts(self.neighbor)["confirmations"], 1)
        self.assertEqual(ai.effective_confirmations(self.report), [])

    def test_inactive_field_is_shown_as_excluded_and_cannot_be_saved(self):
        FieldDefinition.objects.filter(key="entrance_available").update(is_active=False)
        keys = [k for k in KEYS if k != "entrance_available"]
        analysis, _ = ai.analyze(self.report, self.staff,
                                 client=FakeClient(body(output(keys=keys, step_height_cm=clear(3)))))
        self.assertNotIn("entrance_available", analysis.result["fields"])
        with self.assertRaises(ai.AIError):
            ai.save_selection(analysis, self.staff, {"entrance_available": True})
        self.client.force_login(self.staff)
        page = self.client.get(reverse("ops:report-review", args=[self.report.pk]))
        self.assertContains(page, "분석 제외")
        self.assertNotContains(page, 'value="entrance_available"')


class NoticeTokenTests(AIBase):
    """제보 폼의 안내 버전 표 (명세 v1.3 7.1)"""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.neighbor)  # resident는 setUp에서 이미 제보해 24시간 제한에 걸림
        self.url = reverse("reports:new")

    def post(self, token, **extra):
        data = {"place": self.place.pk, "step_height_cm": "0", "photo": photo(), **extra}
        if token is not None:
            data["notice_token"] = token
        return self.client.post(self.url, data)

    def test_valid_token_records_version(self):
        page = self.client.get(self.url, {"place": self.place.pk})
        token = page.context["form"].notice_token_value
        self.assertContains(page, f'name="notice_token" value="{token}"')
        before = Report.objects.count()
        self.assertRedirects(self.post(token), reverse("reports:done"))
        self.assertEqual(Report.objects.count(), before + 1)
        self.assertEqual(Report.objects.latest("pk").ai_notice_version, "notice-test-1")

    def test_missing_tampered_or_old_tokens_are_rejected(self):
        with override_settings(AI_NOTICE_VERSION="notice-old"):
            old = ai.notice_token()
        before = Report.objects.count()
        for token in (None, "tampered", old):
            with self.subTest(token=token):
                res = self.post(token)
                self.assertEqual(res.status_code, 200)
                self.assertContains(res, "AI 활용 안내가 바뀌었거나 확인되지 않았어요")
                self.assertContains(res, f'value="{res.context["form"].notice_token_value}"')  # 새 표로 다시
        self.assertEqual(Report.objects.count(), before)

    @override_settings(AI_ENABLED=False)
    def test_no_token_needed_when_ai_off(self):
        self.assertRedirects(self.post(None), reverse("reports:done"))
        self.assertEqual(Report.objects.latest("pk").ai_notice_version, "")


def gemini_body(data, finish="STOP", text=None, **extra):
    return {"responseId": "gem_test", "candidates": [{"finishReason": finish, "content": {"role": "model", "parts": [
        {"text": text if text is not None else json.dumps(data, ensure_ascii=False)}]}}],
            "usageMetadata": {"promptTokenCount": 900, "candidatesTokenCount": 150, "totalTokenCount": 1050}, **extra}


class GeminiTests(AIBase):
    """Google Gemini 호출부 (AI_PROVIDER=gemini, 결제 연결한 유료 등급 키)"""

    def response(self, status, payload):
        res = mock.Mock(status_code=status)
        res.json.return_value = payload
        return res

    def test_schema_is_converted_to_gemini_form_without_changing_meaning(self):
        schema = ai.gemini_schema(ai.output_schema(ai.active_definitions()))
        text = json.dumps(schema, ensure_ascii=False)
        self.assertNotIn('"null"]', text)  # ["number", "null"] 같은 배열 type 없음
        fields = schema["properties"]["fields"]
        self.assertEqual(fields["required"], KEYS)
        door = fields["properties"]["door_type"]["properties"]["value"]
        self.assertEqual(door["anyOf"][1], {"type": "null"})
        self.assertNotIn(None, door["anyOf"][0]["enum"])
        self.assertNotIn("자동문", door["anyOf"][0]["enum"])
        self.assertNotIn("enum", fields["properties"]["has_ramp"]["properties"]["needs_manual_check"])
        self.assertEqual(fields["properties"]["step_count"]["properties"]["value"]["anyOf"][0], {"type": "integer"})

    @override_settings(AI_PROVIDER="gemini")
    def test_analyze_with_gemini_end_to_end(self):
        data = output(step_height_cm=clear(3), has_ramp=clear(False))
        with mock.patch("reports.ai.requests.post", return_value=self.response(200, gemini_body(data))) as post:
            analysis, _ = ai.analyze(self.report, self.staff)
        url, kwargs = post.call_args.args[0], post.call_args.kwargs
        self.assertIn("models/gemini-3-flash-preview:generateContent", url)
        self.assertEqual(kwargs["headers"], {"x-goog-api-key": "gemini-test-key"})  # 키는 주소가 아니라 헤더로
        self.assertEqual(kwargs["timeout"], ai.OPENAI_TIMEOUT)
        sent = kwargs["json"]
        parts = sent["contents"][0]["parts"]
        self.assertIn("[전화번호]", parts[0]["text"])
        self.assertNotIn("010-1234-5678", json.dumps(sent, ensure_ascii=False))
        self.assertEqual(parts[1]["inline_data"]["mime_type"], "image/jpeg")
        self.assertEqual(sent["generationConfig"]["responseMimeType"], "application/json")
        self.assertIn("system_instruction", sent)
        self.assertEqual(analysis.status, AIAnalysis.Status.SUCCEEDED)
        self.assertEqual(analysis.model_id, "gemini:gemini-3-flash-preview")
        self.assertEqual(analysis.usage, {"input_tokens": 900, "output_tokens": 150, "total_tokens": 1050})
        self.assertEqual(analysis.result["fields"]["step_height_cm"]["value"], 3)

    def test_gemini_response_states(self):
        good_data = output()
        self.assertEqual(ai.parse_gemini_response(gemini_body(good_data))[1], "gem_test")
        thought = gemini_body(good_data)
        thought["candidates"][0]["content"]["parts"].insert(0, {"text": "생각 중", "thought": True})
        self.assertEqual(ai.parse_gemini_response(thought)[0]["report_type"], "ACCESSIBILITY_OBSERVATION")
        cases = {
            "AI_INCOMPLETE": gemini_body(good_data, finish="MAX_TOKENS"),
            "AI_REFUSAL": gemini_body(good_data, finish="SAFETY"),
            "AI_REFUSAL ": {"promptFeedback": {"blockReason": "SAFETY"}},
            "AI_INVALID_OUTPUT": gemini_body(None, text="JSON 아님"),
            "AI_INVALID_OUTPUT ": {"candidates": []},
            "AI_INVALID_OUTPUT  ": gemini_body(None, text='{"a": 1, "a": 2}'),
        }
        for code, response in cases.items():
            with self.subTest(code=code), self.assertRaises(ai.AIError) as e:
                ai.parse_gemini_response(response)
            self.assertEqual(e.exception.code, code.strip())

    @override_settings(AI_PROVIDER="gemini")
    def test_gemini_http_errors(self):
        cases = [
            (dict(side_effect=requests.Timeout()), "AI_TIMEOUT"),
            (dict(return_value=self.response(429, {"error": {"status": "RESOURCE_EXHAUSTED",
                                                             "message": "Your prepayment credits are depleted."}})),
             "AI_BUDGET_EXCEEDED"),
            (dict(return_value=self.response(429, {"error": {"status": "RESOURCE_EXHAUSTED",
                                                             "message": "Quota exceeded for requests per minute."}})),
             "AI_UNAVAILABLE"),
            (dict(return_value=self.response(400, {"error": {"status": "INVALID_ARGUMENT", "message": "bad key"}})),
             "AI_UNAVAILABLE"),
        ]
        for post, code in cases:
            with self.subTest(code=code), mock.patch("reports.ai.requests.post", **post), \
                    mock.patch("reports.ai.logger"), self.assertRaises(ai.AIError) as e:
                ai.GeminiClient().create(REQUEST)
            self.assertEqual(e.exception.code, code)

    def test_provider_settings_and_notice_recipient(self):
        with override_settings(AI_PROVIDER="gemini"):
            self.assertIn("Google(미국)", ai.notice_text())
            self.assertIsNone(ai.config_error())
            with override_settings(GEMINI_API_KEY=""):
                self.assertEqual(ai.config_error(), "AI_UNAVAILABLE")
        with override_settings(AI_PROVIDER="claude"):
            self.assertEqual(ai.config_error(), "AI_UNAVAILABLE")
        self.assertIn("OpenAI(미국)", ai.notice_text())

    def test_switching_provider_does_not_reuse_old_result(self):
        ai.analyze(self.report, self.staff, client=good())
        with override_settings(AI_PROVIDER="gemini"):
            client = good()
            _, reused = ai.analyze(self.report, self.staff, client=client)
        self.assertFalse(reused)
        self.assertEqual(len(client.calls), 1)

    @override_settings(AI_PROVIDER="gemini")
    def test_screens_name_google_as_recipient(self):
        self.client.force_login(self.staff)
        page = self.client.get(reverse("ops:report-review", args=[self.report.pk]))
        self.assertContains(page, "<strong>Google(미국)</strong>로 전송돼요")
        self.client.force_login(self.neighbor)
        page = self.client.get(reverse("reports:new"), {"place": self.place.pk})
        self.assertContains(page, "Google(미국)로 전송될 수 있습니다")

    def test_generation_config_per_model_family(self):
        with override_settings(GEMINI_MODEL="gemini-3-flash-preview"):
            config = ai.GeminiClient().generation_config(REQUEST)
        self.assertEqual(config["thinkingConfig"], {"thinkingLevel": "low"})
        self.assertNotIn("temperature", config)  # Gemini 3은 기본 1.0 그대로 (구글 권장)
        self.assertEqual(config["maxOutputTokens"], ai.GEMINI3_MAX_OUTPUT_TOKENS)
        with override_settings(GEMINI_MODEL="gemini-3.8-flash", GEMINI_THINKING_LEVEL="minimal"):
            self.assertEqual(ai.GeminiClient().generation_config(REQUEST)["thinkingConfig"], {"thinkingLevel": "minimal"})
        with override_settings(GEMINI_MODEL="gemini-2.5-flash-lite"):
            config = ai.GeminiClient().generation_config(REQUEST)
        self.assertEqual((config["temperature"], config["maxOutputTokens"]), (0, 2500))
        self.assertNotIn("thinkingConfig", config)
