"""
AI 판별 설정 비교 실험 (운영자용)

같은 제보 사진·설명을 여러 설정으로 Gemini에 보내 결과를 나란히 보여 준다.
"AI가 계단·손잡이·문을 잘 못 알아본다"의 원인이 모델 등급인지, 생각 단계인지, 이미지 해상도인지,
일부러 엄격하게 만든 지시문(추정 금지·확신 없으면 비움) 때문인지 가려내려는 것.

  - DB에는 아무것도 저장하지 않는다 (AIAnalysis·일일 횟수·제보 값 그대로)
  - API 키 값, 주민 설명 원문, AI 근거 문장은 출력하지 않는다 (개인정보·사진 속 글자 노출 방지)
  - 외부 전송 조건은 운영 분석과 같다: AI 안내를 보고 제출한 주민 제보만 보낸다 (reports/ai.py unsupported_reason)
    단, 이미 처리(승인·반려)된 제보도 정답 비교용으로 쓴다
  - 비용: 조건 수 × 제보 수 만큼 호출 (기본 5조건 × 5건 = 25회)

조건
  A 지금 설정 그대로 (GEMINI_MODEL, GEMINI_THINKING_LEVEL)
  B 생각 단계만 high
  C 모델만 상위 모델 (--flash-model, 기본 gemini-3.5-flash)
  D 지시문만 완화 (보이는 것은 답하기. cm·각도 추정 금지는 그대로)
  E 이미지 해상도만 높게 (mediaResolution HIGH)

  python manage.py compare_ai                          # 최근 사진 제보 5건 × A~E
  python manage.py compare_ai --reports 12,15          # 특정 제보만
  python manage.py compare_ai --conditions A,C --limit 3
"""

import re
import time
import unicodedata
from collections import defaultdict
from decimal import Decimal

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from reports import ai
from reports.models import Report

# 완화 지시문: 기존 규칙 줄을 찾아 바꾼다 (찾을 문구 → 바꿀 문구). 못 찾으면 실행 전에 알려 준다
RELAX = [
    ("null은 모름이다.",
     "사진에 보이는 것은 적극적으로 답한다. 사진에 찍히지 않은 부분만 null로 둔다. 사진에서 분명히 보이면 certainty=CLEAR로 한다."),
    ("step_count는",
     "step_count는 사진에 보이는 입구 계단 칸 수를 센다. 계단·턱 없이 평평하면 0."),
    ("사진에 안 보인다는 이유로 false라고 하지 않는다.",
     "{keys}는 사진에 보이면 true, 그 부분이 잘 보이는데 없으면 false, 사진에 그 부분이 안 찍혔으면 null."),
]
CERT = {"CLEAR": "", "UNCERTAIN": "?", "UNKNOWN": "-"}


def pad(text, width, left=False):
    """터미널 표 정렬: 한글은 두 칸으로 센다"""
    size = sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)
    space = " " * max(0, width - size)
    return space + text if left else text + space


def relaxed(instructions):
    """규칙 줄(번호. 내용) 단위로 바꾼다. 바꾼 개수도 돌려줌"""
    lines, changed = [], 0
    for line in instructions.split("\n"):
        for marker, new in RELAX:
            if marker in line:
                number = re.match(r"^\d+\. ", line)
                keys = re.match(r"^(?:\d+\. )?(.+?)는 사진에 분명히", line)
                line = (number.group(0) if number else "") + new.format(keys=keys.group(1) if keys else "해당 항목")
                changed += 1
                break
        lines.append(line)
    return "\n".join(lines), changed


def call_gemini(request, model, thinking, media_high):
    """운영 GeminiClient와 같은 요청에 설정만 바꿔 보낸다 → (결과, 원래 출력, 사용량, 초) 또는 오류 문자열"""
    payload = ai.GeminiClient().payload(request)
    config = {"responseMimeType": "application/json", "responseJsonSchema": ai.gemini_schema(request["schema"])}
    if model.startswith("gemini-2"):
        config.update(maxOutputTokens=request["max_output_tokens"], temperature=0)
    else:
        config.update(maxOutputTokens=ai.GEMINI3_MAX_OUTPUT_TOKENS, thinkingConfig={"thinkingLevel": thinking})
    if media_high:
        config["mediaResolution"] = "MEDIA_RESOLUTION_HIGH"
    payload["generationConfig"] = config
    url = ai.GEMINI_URL.format(model=requests.utils.quote(model, safe="-._"))
    started = time.monotonic()
    try:
        status, body = ai._post(url, payload, {"x-goog-api-key": settings.GEMINI_API_KEY}, "Gemini")
        if status:
            return f"HTTP {status} {body.get('status') or ''} {str(body.get('message') or '')[:120]}".strip()
        data, _, usage = ai.parse_gemini_response(body)
        return ai.validate_output(data, request["_defs"]), data, usage or {}, time.monotonic() - started
    except ai.AIError as e:
        return e.code


def same(answer, truth):
    if answer is None or truth is None:
        return None
    if isinstance(truth, Decimal) or isinstance(answer, (int, float)) and not isinstance(answer, bool):
        try:
            return Decimal(str(answer)) == Decimal(str(truth))
        except ArithmeticError:
            return False
    return answer == truth


class Command(BaseCommand):
    help = "같은 제보 사진을 여러 AI 설정으로 분석해 비교한다 (DB 저장 없음, 호출 비용 발생)"

    def add_arguments(self, parser):
        parser.add_argument("--reports", default="", help="제보 번호 (쉼표 구분). 비우면 최근 사진 제보")
        parser.add_argument("--limit", type=int, default=5, help="제보 번호를 안 줬을 때 고를 개수 (기본 5)")
        parser.add_argument("--conditions", default="A,B,C,D,E", help="돌릴 조건 (기본 A,B,C,D,E)")
        parser.add_argument("--flash-model", default="gemini-3.5-flash", help="조건 C의 상위 모델 (기본 gemini-3.5-flash)")

    def handle(self, *args, **options):
        if settings.AI_PROVIDER != "gemini" or not settings.GEMINI_API_KEY or not settings.GEMINI_MODEL:
            raise CommandError("AI_PROVIDER=gemini, GEMINI_API_KEY, GEMINI_MODEL 이 설정돼 있어야 해요.")
        base_model, base_thinking = settings.GEMINI_MODEL, settings.GEMINI_THINKING_LEVEL
        catalog = {
            "A": ("지금 설정", base_model, base_thinking, False, False),
            "B": ("생각 high", base_model, "high", False, False),
            "C": (f"모델 {options['flash_model']}", options["flash_model"], base_thinking, False, False),
            "D": ("지시문 완화", base_model, base_thinking, True, False),
            "E": ("해상도 HIGH", base_model, base_thinking, False, True),
        }
        names = [c.strip().upper() for c in options["conditions"].split(",") if c.strip()]
        if not names or any(n not in catalog for n in names):
            raise CommandError(f"조건은 {', '.join(catalog)} 중에서 골라 주세요.")
        conditions = {n: catalog[n] for n in names}

        reports = self.pick(options)
        if not reports:
            raise CommandError("비교할 수 있는 제보가 없어요 (AI 안내를 보고 제출한 사진 제보만 보낼 수 있어요).")
        self.stdout.write(f"지금 설정: 모델 {base_model} · 생각 {base_thinking} · 키 설정됨")
        self.stdout.write(f"제보 {len(reports)}건 × 조건 {len(conditions)}개 = 호출 {len(reports) * len(conditions)}회")
        for n, (label, model, thinking, relax, media) in conditions.items():
            self.stdout.write(f"  {n} {label}: {model} · 생각 {thinking}{' · 지시문 완화' if relax else ''}{' · 해상도 HIGH' if media else ''}")
        self.stdout.write("표 읽는 법: 값 그대로 = 확신(CLEAR, 운영 화면에 후보로 나옴) / 값? = 불확실해서 운영에선 비움 / - = 모름\n")

        stats = defaultdict(lambda: defaultdict(float))
        for report in reports:
            self.compare(report, conditions, stats)
        self.summary(conditions, stats)

    def pick(self, options):
        """운영 분석과 같은 외부 전송 조건 (처리 상태만 예외)"""
        if options["reports"]:
            ids = [int(i) for i in options["reports"].split(",") if i.strip().isdigit()]
            candidates = list(Report.objects.filter(pk__in=ids).order_by("-pk"))
        else:
            candidates = Report.objects.exclude(photo="").order_by("-pk")
        picked = []
        for report in candidates:
            status = report.status
            report.status = Report.Status.PENDING  # 메모리에서만 바꿔 나머지 조건을 검사 (저장하지 않음)
            reason = ai.unsupported_reason(report)
            report.status = status
            if reason or not report.photo:
                if options["reports"]:
                    self.stdout.write(f"제보 {report.pk}: 건너뜀 ({reason or '사진 없음'})")
                continue
            picked.append(report)
            if not options["reports"] and len(picked) >= options["limit"]:
                break
        return picked

    def compare(self, report, conditions, stats):
        defs = ai.active_definitions(report)
        base = ai.build_request(report, defs)
        base["_defs"] = defs
        truth = {v.field_id: v.value for v in report.values.select_related("field")}
        self.stdout.write(f"\n■ 제보 {report.pk} · {ai.analysis_kind(report)} · {report.get_status_display()} · "
                          f"설명 {len(report.note.strip())}자 · 제보값 {len(truth)}개 (주민 입력. AI로 채우기를 썼다면 AI 값일 수 있음)")
        results = {}
        for n, (label, model, thinking, relax, media) in conditions.items():
            request = dict(base)
            if relax:
                request["instructions"], changed = relaxed(base["instructions"])
                if not changed:
                    self.stdout.write(f"  (조건 {n}: 바꿀 규칙을 못 찾아 지금 지시문 그대로 — reports/ai.py 지시문이 바뀌었는지 확인)")
            out = call_gemini(request, model, thinking, media)
            results[n] = out
            s = stats[n]
            s["calls"] += 1
            if isinstance(out, str):
                s["errors"] += 1
                self.stdout.write(f"  {n} 실패: {out}")
                continue
            result, raw, usage, seconds = out
            s["seconds"] += seconds
            s["in_tokens"] += usage.get("input_tokens", 0)
            s["out_tokens"] += usage.get("output_tokens", 0)
            s["ok"] += 1
            for f in defs:
                final = result["fields"][f.key]["value"]
                seen = raw["fields"][f.key]["value"]
                s["clear"] += final is not None
                s["seen"] += seen is not None
                match = same(final, truth.get(f.key))
                if match is not None:
                    s["compared"] += 1
                    s["correct"] += match
                elif f.key in truth and truth[f.key] is not None:
                    s["missed"] += 1

        width = max(len(f.label) for f in defs) * 2
        header = f"  {pad('항목', width)} | {pad('제보값', 8, True)} | " + " | ".join(pad(n, 8, True) for n in conditions)
        self.stdout.write(header)
        for f in defs:
            cells = []
            for n in conditions:
                out = results[n]
                if isinstance(out, str):
                    cells.append(pad("오류", 8, True))
                    continue
                item = out[1]["fields"][f.key]
                value = "" if item["value"] is None else self.short(item["value"])
                cells.append(pad((value + CERT.get(item["certainty"], "?")) or "-", 8, True))
            truth_cell = self.short(truth[f.key]) if truth.get(f.key) is not None else ""
            self.stdout.write(f"  {pad(f.label, width)} | {pad(truth_cell, 8, True)} | " + " | ".join(cells))

    @staticmethod
    def short(value):
        if isinstance(value, bool):
            return "예" if value else "아니오"
        if isinstance(value, Decimal):
            return format(value.normalize(), "f")
        return str(value)[:8]

    def summary(self, conditions, stats):
        self.stdout.write("\n■ 조건별 요약")
        self.stdout.write("  확신 값 = 운영 화면에 후보로 나오는 값 수 / 본 값 = 불확실 포함 AI가 값을 낸 수 / "
                          "일치 = 제보값이 있는 항목 중 확신 값이 같은 수 / 놓침 = 제보값이 있는데 확신 값이 비어 있는 수")
        for n, (label, *_rest) in conditions.items():
            s = stats[n]
            ok = int(s["ok"]) or 1
            self.stdout.write(
                f"  {n} {label}: 성공 {int(s['ok'])}/{int(s['calls'])} · 확신 값 {int(s['clear'])} · 본 값 {int(s['seen'])} · "
                f"일치 {int(s['correct'])}/{int(s['compared'])} · 놓침 {int(s['missed'])} · "
                f"평균 {s['seconds'] / ok:.1f}초 · 입력 {s['in_tokens'] / ok:.0f}토큰 · 출력 {s['out_tokens'] / ok:.0f}토큰")
        self.stdout.write("  입력 토큰이 E에서 크게 늘면 지금은 사진을 낮은 해상도로 보고 있다는 뜻이에요.")
