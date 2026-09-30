"""
이미 올라온 제보 사진의 EXIF(촬영 위치 GPS·기기 정보)를 지운다. 새 사진은 저장할 때 자동으로 지워지므로
(reports.models.Report.save) 이 명령은 그 전에 올라온 사진을 위해 한 번만 실행하면 된다.

    python manage.py strip_photo_exif --dry-run   # 몇 장이 대상인지 보기만
    python manage.py strip_photo_exif             # 실제로 정리
"""

from django.core.management.base import BaseCommand
from PIL import Image, UnidentifiedImageError

from core.images import PHOTO_MAX_PX, normalize_photo
from reports.models import Report


def needs_cleanup(field_file):
    """EXIF가 남아 있거나 기준보다 큰 사진이면 True"""
    with field_file.open("rb") as f, Image.open(f) as im:
        return len(im.getexif()) > 0 or max(im.size) > PHOTO_MAX_PX


class Command(BaseCommand):
    help = "이미 올라온 제보 사진의 EXIF(촬영 위치 등)를 지우고 크기를 줄인다"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="대상 수만 세고 바꾸지 않음")

    def handle(self, *args, dry_run=False, **options):
        cleaned = skipped = broken = 0
        for report in Report.objects.exclude(photo="").only("id", "photo"):
            photo = report.photo
            try:
                if not needs_cleanup(photo):
                    skipped += 1
                    continue
                if not dry_run:
                    with photo.open("rb") as f:
                        new = normalize_photo(f, name=photo.name)
                    old_name = photo.name
                    storage = photo.storage
                    photo.save(new.name, new, save=False)         # 새 파일로 저장 (모델 save 는 거치지 않음)
                    Report.objects.filter(pk=report.pk).update(photo=photo.name)
                    if old_name != photo.name:
                        storage.delete(old_name)                   # EXIF 든 원본은 지움
                cleaned += 1
            except (FileNotFoundError, UnidentifiedImageError, OSError):
                broken += 1
        verb = "정리 대상" if dry_run else "정리"
        self.stdout.write(self.style.SUCCESS(f"{verb} {cleaned}장 · 이미 깨끗함 {skipped}장 · 열 수 없음 {broken}장"))
