"""AI 설정 비교 명령 (compare_ai). 가짜 응답만 쓴다 → 키·네트워크·비용 없음"""

import json
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from . import ai
from .management.commands.compare_ai import relaxed
from .models import AIAnalysis, Report
from .test_ai import AIBase, clear, gemini_body, output


@override_settings(AI_PROVIDER="gemini")
class CompareAITests(AIBase):
    def response(self, status, payload):
        res = mock.Mock(status_code=status)
        res.json.return_value = payload
        return res

    def run_command(self, *args, responses):
        out = StringIO()
        with mock.patch("reports.ai.requests.post", side_effect=responses) as post:
            call_command("compare_ai", *args, stdout=out)
        return out.getvalue(), post

    def test_compares_conditions_without_saving_or_leaking(self):
        good = gemini_body(output(step_height_cm=clear(5), has_ramp={**clear(False), "certainty": "UNCERTAIN"}))
        text, post = self.run_command("--reports", str(self.report.pk), "--conditions", "A,B,C,D,E",
                                      responses=[self.response(200, good)] * 4 + [self.response(404, {"error": {
                                          "status": "NOT_FOUND", "message": "models/x is not found"}})])
        self.assertEqual(post.call_count, 5)
        sent = [c.kwargs["json"] for c in post.call_args_list]
        urls = [c.args[0] for c in post.call_args_list]
        self.assertEqual(sent[1]["generationConfig"]["thinkingConfig"]["thinkingLevel"], "high")      # B
        self.assertIn("models/gemini-3.5-flash:generateContent", urls[2])                            # C
        self.assertNotEqual(sent[3]["system_instruction"], sent[0]["system_instruction"])          # D
        self.assertEqual(sent[4]["generationConfig"]["mediaResolution"], "MEDIA_RESOLUTION_HIGH")   # E
        self.assertNotIn("mediaResolution", sent[0]["generationConfig"])
        self.assertIn("E 실패: HTTP 404 NOT_FOUND", text)
        self.assertIn("일치 1/1", text)  # 단차 5cm = 제보값 5
        self.assertIn("아니오?", text)    # 불확실한 값은 ? 표시 (운영에선 비움)
        # 키·설명 원문을 출력하지 않고, DB에는 아무것도 남기지 않음
        self.assertNotIn("gemini-test-key", text)
        self.assertNotIn("010-1234-5678", text)
        self.assertNotIn("010-1234-5678", json.dumps(sent, ensure_ascii=False))
        self.assertFalse(AIAnalysis.objects.exists())
        self.assertEqual(Report.objects.get(pk=self.report.pk).status, Report.Status.PENDING)

    def test_only_reports_with_ai_notice_are_sent(self):
        old = self.make_report(ai_notice_version="")
        verified = self.make_report(status=Report.Status.VERIFIED)
        text, post = self.run_command("--reports", f"{old.pk},{verified.pk}", "--conditions", "A",
                                      responses=[self.response(200, gemini_body(output()))])
        self.assertIn(f"제보 {old.pk}: 건너뜀 (NOTICE_NOT_APPLIED)", text)
        self.assertEqual(post.call_count, 1)  # 처리된 제보는 정답 비교용으로 보냄
        self.assertEqual(Report.objects.get(pk=verified.pk).status, Report.Status.VERIFIED)

    def test_relaxed_instructions_replace_strict_rules(self):
        strict = ai.instructions(ai.active_definitions())
        loose, changed = relaxed(strict)
        self.assertGreaterEqual(changed, 2)
        self.assertNotIn("null은 모름이다.", loose)
        self.assertIn("사진에 보이는 입구 계단 칸 수를 센다", loose)
        self.assertIn("사진의 비율로 cm나 각도를 추정하지 않는다", loose)  # 수치 추정 금지는 그대로

    def test_requires_gemini_settings_and_valid_conditions(self):
        with override_settings(AI_PROVIDER="openai"), self.assertRaises(CommandError):
            call_command("compare_ai", stdout=StringIO())
        with self.assertRaises(CommandError):
            call_command("compare_ai", "--conditions", "Z", stdout=StringIO())
