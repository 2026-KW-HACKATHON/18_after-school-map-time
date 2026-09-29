"""
팀 답사 기록(CSV) 가져오기 (F6). 자세한 사용법: docs/survey-guide.md

    # 1) 검사만 (저장 안 함, 판정 결과 미리 보기)
    python manage.py import_survey places/data/survey/wolgye1.csv --photos 사진폴더 --dry-run
    # 2) 실제로 넣기
    python manage.py import_survey places/data/survey/wolgye1.csv --photos 사진폴더 --user 운영자아이디
    # 빈 양식 다시 만들기 (필드 정의를 바꿨을 때)
    python manage.py import_survey --template places/data/survey/template.csv
"""

import csv

from django.core.management.base import BaseCommand, CommandError

from accounts.models import User
from ops.survey_import import SurveyError, import_survey, template_rows
from places.models import Region


class Command(BaseCommand):
    help = "팀 답사 기록 CSV를 장소·접근성 값으로 넣는다 (같은 파일을 다시 넣어도 중복되지 않음)"

    def add_arguments(self, parser):
        parser.add_argument("csv_path", nargs="?", help="답사 CSV 파일")
        parser.add_argument("--photos", help="'입구 사진' 칸의 파일이 들어 있는 폴더")
        parser.add_argument("--region", default="wolgye1", help="지역 코드 (기본: wolgye1)")
        parser.add_argument("--user", help="기록에 남길 작성자(운영자) 아이디")
        parser.add_argument("--dry-run", action="store_true", help="검사와 판정 미리 보기만 하고 저장하지 않음")
        parser.add_argument("--template", metavar="PATH", help="빈 답사 양식 CSV를 만든다")

    def handle(self, *args, **opts):
        if opts["template"]:
            # utf-8-sig: 엑셀에서 열어도 한글이 깨지지 않게 BOM을 붙인다
            with open(opts["template"], "w", encoding="utf-8-sig", newline="") as f:
                csv.writer(f).writerows(template_rows())
            self.stdout.write(self.style.SUCCESS(f"양식을 만들었어요: {opts['template']}"))
            return
        if not opts["csv_path"]:
            raise CommandError("CSV 파일 경로를 알려 주세요. 예: python manage.py import_survey 답사.csv --dry-run")

        region = Region.objects.filter(code=opts["region"]).first()
        if region is None:
            raise CommandError(f"지역 '{opts['region']}'이 없어요. 먼저 python manage.py seed_base")
        user = None
        if opts["user"]:
            user = User.objects.filter(username=opts["user"]).first()
            if user is None:
                raise CommandError(f"아이디 '{opts['user']}'인 사용자가 없어요")

        try:
            result = import_survey(opts["csv_path"], region=region, photos_dir=opts["photos"], user=user,
                                   dry_run=opts["dry_run"])
        except SurveyError as e:
            for line in e.errors:
                self.stderr.write(f"  - {line}")
            raise CommandError(f"고칠 곳이 {len(e.errors)}개 있어요. 아무것도 저장하지 않았어요.")
        except FileNotFoundError as e:
            raise CommandError(f"파일이 없어요: {e.filename}")

        for row in result.rows:
            self.stdout.write(f"{row['line']:>3}줄  [{row['status']}] {row['name']}")
            for profile, label, reason in row["judgments"]:
                self.stdout.write(f"        {profile}: {label}" + (f" — {reason}" if reason else ""))
        summary = (f"새 장소 {result.count('새 장소')}곳 · 갱신 {result.count('갱신')}곳 · "
                   f"변경 없음 {result.count('변경 없음')}곳 · 답사 기록 {result.reports}건")
        if opts["dry_run"]:
            self.stdout.write(self.style.WARNING(f"[검사만 함 — 저장 안 됨] {summary}"))
        else:
            self.stdout.write(self.style.SUCCESS(summary))
