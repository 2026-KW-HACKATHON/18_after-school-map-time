"""
공공데이터(장애인편의시설 현황)에서 월계동 시설 가져오기. 자세한 설명: places/public_data.py

    # 레포에 넣어 둔 받은 내용(스냅숏)으로 — 공공데이터포털 호출 0회, 누가 해도 같은 결과
    python manage.py import_public_facilities --cache places/data/public/wolgye-facilities-20261001.json --dry-run
    python manage.py import_public_facilities --cache places/data/public/wolgye-facilities-20261001.json
    # 새로 받기 (키 필요): 없는 파일 이름을 주면 받아서 그 파일에 저장
    python manage.py import_public_facilities --cache /tmp/new.json --dry-run

하루 호출 수(개발 계정 100회)를 넘지 않게 --limit 으로 끊고, 이미 가져온 시설은 다시 부르지 않는다.
"""

from django.core.management.base import BaseCommand, CommandError

from places.models import Region
from places.public_data import PublicDataError, import_facilities, imported_ids, load_or_fetch


class Command(BaseCommand):
    help = "공공데이터포털 장애인편의시설 현황에서 지역 시설을 가져온다 (주거시설 제외)"

    def add_arguments(self, parser):
        parser.add_argument("--sido", default="서울특별시")
        parser.add_argument("--sigungu", default="노원구")
        parser.add_argument("--dong-code", default="1135010200", help="법정동 코드 = 시설ID 앞 10자리 (기본: 노원구 월계동)")
        parser.add_argument("--region", default="wolgye1", help="넣을 지역 코드")
        parser.add_argument("--limit", type=int, default=90, help="이번에 쓸 최대 호출 수 (하루 100회 제한)")
        parser.add_argument("--cache", help="받은 내용을 저장·재사용할 JSON 파일")
        parser.add_argument("--dry-run", action="store_true", help="저장하지 않고 미리 보기")
        parser.add_argument("--radius", type=int, help="지역 중심에서 이 거리(미터) 안 시설만 (기본: 법정동 전체)")

    def handle(self, *args, **o):
        region = Region.objects.filter(code=o["region"]).first()
        if region is None:
            raise CommandError(f"지역 '{o['region']}'이 없어요. 먼저 python manage.py seed_base")
        try:
            data, calls = load_or_fetch(o["cache"], o["sido"], o["sigungu"], o["dong_code"], o["limit"], imported_ids())
        except PublicDataError as e:
            raise CommandError(str(e))
        self.stdout.write(f"공공데이터포털 호출 {calls}회 · 시설 {len(data)}곳" + (f" (파일: {o['cache']})" if o["cache"] else ""))

        rows = import_facilities(data, region, dry_run=o["dry_run"], radius_m=o["radius"])
        for r in rows:
            self.stdout.write(f"  [{r.status}] {r.name}" + (f" — {r.note}" if r.note else ""))
            for profile, label in r.judgments:
                self.stdout.write(f"        {profile}: {label}")
        counts = {s: sum(1 for r in rows if r.status == s) for s in ("새 장소", "갱신", "변경 없음", "건너뜀")}
        summary = " · ".join(f"{k} {v}곳" for k, v in counts.items())
        if o["dry_run"]:
            self.stdout.write(self.style.WARNING(f"[검사만 함 — 저장 안 됨] {summary}"))
        else:
            self.stdout.write(self.style.SUCCESS(summary))
