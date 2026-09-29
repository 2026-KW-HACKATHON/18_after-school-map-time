"""
팀 답사 기록(CSV) 가져오기 (F6). 한 줄 = 장소 하나.

- 답사 시트를 엑셀·구글 시트로 채운 뒤 CSV로 저장해서 넣는다 (양식: places/data/survey/template.csv)
- 값은 운영자 장소 등록과 똑같이 '팀 답사' 제보(VERIFIED)로 저장한다 → 이력이 남고, 이후 주민 제보로 갱신된다
- 전부 검사한 뒤 문제가 하나라도 있으면 아무것도 저장하지 않는다 (반쯤 들어간 상태를 만들지 않기)
- 같은 파일을 다시 넣어도 중복되지 않는다: 이름+주소가 같으면 같은 장소, 값과 확인일이 같으면 건너뜀

칸 이름은 접근성 필드 정의(FieldDefinition)의 이름에서 만든다 → 필드를 추가하면 양식에도 자동으로 칸이 생긴다.
"""

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

import requests
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from PIL import Image, ImageOps, UnidentifiedImageError

from judgments.constants import display
from judgments.receivers import affected_places
from judgments.engine import recompute_place
from places.models import Building, Entrance, FieldDefinition, Place, Region
from reports.models import Report
from reports.selectors import current_values

from .services import _save_values, _survey_report, main_entrance, observed_at_for

# 장소·건물 기본 정보 칸 (접근성 값 칸은 FieldDefinition에서 만든다)
PLACE_COLUMNS = ["이름", "유형", "주소", "위도", "경도", "층", "전화번호", "확인일", "답사자", "메모", "입구 사진"]
BUILDING_COLUMNS = ["건물 이름", "건물 주소"]
BUILDING_ENTRANCE_PREFIX = "건물 "  # 2층 이상 가게: 건물 공용 입구 값은 "건물 입구 단차(cm)"처럼 적는다

TRUE_WORDS = {"있음", "예", "o", "y", "yes", "true"}
FALSE_WORDS = {"없음", "아니오", "x", "n", "no", "false"}
UNKNOWN_WORDS = {"", "모름", "-", "?"}  # 모르면 비워 둔다 → 그 값은 건드리지 않음

# 월계1동 근처인지 대략 확인 (위도·경도를 바꿔 적는 실수 잡기). 한국 전체 범위
LAT_RANGE = (Decimal("33"), Decimal("39"))
LNG_RANGE = (Decimal("124"), Decimal("132"))
COORD = Decimal("0.000001")

PHOTO_MAX_PX = 1600  # 폰 사진(4000px·수 MB)을 줄여 저장 공간·모바일 데이터 절약
KAKAO_ADDRESS_URL = "https://dapi.kakao.com/v2/local/search/address.json"


class SurveyError(Exception):
    """CSV에 고칠 곳이 있음. errors: ["3번째 줄: ..."]"""

    def __init__(self, errors):
        super().__init__("\n".join(errors))
        self.errors = errors


# ── 1. 양식 (칸 이름) ─────────────────────────────────────


def _fields(scope):
    return list(FieldDefinition.objects.filter(scope=scope, is_active=True).order_by("order", "key"))


def _header(f):
    return f"{f.label}({f.unit})" if f.unit else f.label


def _normalize(header):
    """'입구 단차 (cm)' → '입구 단차'. 단위 괄호와 앞뒤 공백은 무시한다"""
    return re.sub(r"\s*\(.*\)\s*$", "", (header or "").strip())


def template_header():
    """답사 양식의 칸 이름 순서: 장소 정보 → 가게 입구 → 가게 안 → 건물 정보 → 건물 입구 → 건물 공용"""
    S = FieldDefinition.Scope
    entrance = _fields(S.ENTRANCE)
    return (
        PLACE_COLUMNS
        + [_header(f) for f in entrance]
        + [_header(f) for f in _fields(S.PLACE)]
        + BUILDING_COLUMNS
        + [BUILDING_ENTRANCE_PREFIX + _header(f) for f in entrance]
        + [_header(f) for f in _fields(S.BUILDING)]
    )


# 양식 둘째 줄 예시. 이름이 '#'으로 시작하는 줄은 읽지 않는다
EXAMPLE = {
    "이름": "# 예시) 월계 약국 - 이 줄은 읽지 않아요", "유형": "약국", "주소": "서울 노원구 월계로 000", "층": "1",
    "확인일": "2026-10-03", "답사자": "강성훈", "메모": "입구 오른쪽에 호출벨", "입구 사진": "wolgye-pharmacy.jpg",
    "입구 단차": "15", "계단 수": "1", "고정 경사로": "없음", "출입문 폭": "90", "출입문 형태": "여닫이",
    "가게 안 단차": "없음", "장애인 화장실": "모름",
}


def template_rows():
    """빈 답사 양식: 칸 이름 줄 + 예시 줄"""
    header = template_header()
    return [header, [EXAMPLE.get(_normalize(h), "") for h in header]]


def _column_map():
    """정규화한 칸 이름 → ("info", 이름) 또는 (값 대상, FieldDefinition)"""
    S = FieldDefinition.Scope
    columns = {name: ("info", name) for name in PLACE_COLUMNS + BUILDING_COLUMNS}
    for f in _fields(S.ENTRANCE):
        columns[f.label] = ("entrance", f)
        columns[BUILDING_ENTRANCE_PREFIX + f.label] = ("building_entrance", f)
    for f in _fields(S.PLACE):
        columns[f.label] = ("place", f)
    for f in _fields(S.BUILDING):
        columns[f.label] = ("building", f)
    return columns


# ── 2. 읽기·검사 ─────────────────────────────────────────


@dataclass
class SurveyRow:
    line: int
    info: dict                                   # 장소·건물 기본 정보 (빈 칸 제외)
    values: dict = field(default_factory=dict)   # {"entrance": {키: 값}, "place": ..., "building": ..., "building_entrance": ...}
    lat: Decimal | None = None
    lng: Decimal | None = None
    observed_on: date | None = None
    photo_path: Path | None = None


def _read_text(path):
    raw = Path(path).read_bytes()
    # 엑셀에서 "CSV"로 저장하면 cp949, "CSV UTF-8"이나 구글 시트는 UTF-8
    for encoding in ("utf-8-sig", "cp949"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise SurveyError(["파일 글자 인코딩을 읽을 수 없어요. 'CSV UTF-8' 형식으로 다시 저장해 주세요."])


def parse_value(f, cell):
    """칸 하나 → 값. 비었거나 '모름'이면 None (그 값은 저장하지 않음). 잘못된 값은 ValueError"""
    cell = (cell or "").strip()
    if cell.lower() in UNKNOWN_WORDS:
        return None
    vt = FieldDefinition.ValueType
    if f.value_type == vt.NUMBER:
        try:
            number = Decimal(cell)
        except InvalidOperation:
            raise ValueError(f"{f.label}: 숫자로 적어 주세요 ('{cell}')")
        if number < 0:
            raise ValueError(f"{f.label}: 0 이상이어야 해요 ('{cell}')")
        return number
    if f.value_type == vt.BOOL:
        word = cell.lower()
        if word in TRUE_WORDS:
            return True
        if word in FALSE_WORDS:
            return False
        raise ValueError(f"{f.label}: '있음' 또는 '없음'으로 적어 주세요 ('{cell}')")
    if f.value_type == vt.CHOICE and cell not in f.choices:
        raise ValueError(f"{f.label}: {', '.join(f.choices)} 중 하나로 적어 주세요 ('{cell}')")
    return cell


def _parse_date(cell):
    try:
        day = date.fromisoformat(re.sub(r"[./]", "-", cell.strip()))
    except ValueError:
        raise ValueError(f"확인일: 2026-10-03 형식으로 적어 주세요 ('{cell}')")
    if day > date.today():
        raise ValueError(f"확인일: 미래 날짜예요 ('{cell}')")
    return day


def _parse_coord(cell, label, low, high):
    try:
        value = Decimal(cell.strip()).quantize(COORD)
    except InvalidOperation:
        raise ValueError(f"{label}: 숫자로 적어 주세요 ('{cell}')")
    if not low <= value <= high:
        raise ValueError(f"{label}: 범위를 벗어났어요 ('{cell}'). 위도·경도를 바꿔 적지 않았는지 확인해 주세요")
    return value


def _parse_row(line, cells, columns, photos_dir):
    row = SurveyRow(line=line, info={})
    errors = []
    for header, cell in cells.items():
        kind, target = columns[_normalize(header)]
        cell = (cell or "").strip()
        try:
            if kind == "info":
                if cell:
                    row.info[target] = cell
            else:
                value = parse_value(target, cell)
                if value is not None:
                    row.values.setdefault(kind, {})[target.key] = value
        except ValueError as e:
            errors.append(str(e))

    info = row.info
    if not info.get("이름"):
        errors.append("이름이 비어 있어요")
    if info.get("유형") and _category(info["유형"]) is None:
        choices = ", ".join(label for _, label in Place.Category.choices)
        errors.append(f"유형: {choices} 중 하나로 적어 주세요 ('{info['유형']}')")
    try:
        if ("위도" in info) != ("경도" in info):
            errors.append("위도와 경도는 둘 다 적거나 둘 다 비워 주세요")
        elif "위도" in info:
            row.lat = _parse_coord(info["위도"], "위도", *LAT_RANGE)
            row.lng = _parse_coord(info["경도"], "경도", *LNG_RANGE)
    except ValueError as e:
        errors.append(str(e))
    if "층" in info and not re.fullmatch(r"-?\d+", info["층"]):
        errors.append(f"층: 정수로 적어 주세요 (지하 1층은 -1) ('{info['층']}')")
    if "확인일" not in info:
        errors.append("확인일이 비어 있어요 (답사한 날짜)")
    else:
        try:
            row.observed_on = _parse_date(info["확인일"])
        except ValueError as e:
            errors.append(str(e))
    has_building = "건물 주소" in info or "건물 이름" in info
    if not has_building and (row.values.get("building") or row.values.get("building_entrance")):
        errors.append("건물 값이 있으면 '건물 주소' 또는 '건물 이름'도 적어 주세요")
    if "입구 사진" in info:
        if photos_dir is None:
            errors.append("입구 사진이 있으면 --photos 로 사진 폴더를 알려 주세요")
        else:
            path = Path(photos_dir) / info["입구 사진"]
            try:
                with Image.open(path) as im:
                    im.verify()
                row.photo_path = path
            except FileNotFoundError:
                errors.append(f"입구 사진: 파일이 없어요 ({path})")
            except (UnidentifiedImageError, OSError):
                errors.append(f"입구 사진: 이미지 파일이 아니에요 ({path})")
    return row, [f"{line}번째 줄: {e}" for e in errors]


def read_survey(path, photos_dir=None):
    """CSV 전체를 읽고 검사한다. 문제가 있으면 SurveyError (모든 줄의 문제를 한 번에 알려 줌)"""
    reader = csv.DictReader(io.StringIO(_read_text(path)))
    columns = _column_map()
    unknown = [h for h in reader.fieldnames or [] if _normalize(h) not in columns]
    if unknown or not reader.fieldnames:
        raise SurveyError([
            f"알 수 없는 칸: {', '.join(unknown) or '(칸 이름 줄이 없음)'}. "
            "양식(places/data/survey/template.csv)의 칸 이름을 그대로 써 주세요"
        ])
    rows, errors = [], []
    for cells in reader:
        cells.pop(None, None)  # 칸 이름보다 많이 적은 값
        name = (cells.get("이름") or "").strip()
        if not any((c or "").strip() for c in cells.values()) or name.startswith("#"):
            continue  # 빈 줄, '#'으로 시작하는 예시·메모 줄은 건너뜀
        row, row_errors = _parse_row(reader.line_num, cells, columns, photos_dir)
        rows.append(row)
        errors += row_errors
    seen = {}
    for row in rows:
        key = (row.info.get("이름"), row.info.get("주소", ""))
        if key in seen:
            errors.append(f"{row.line}번째 줄: {seen[key]}번째 줄과 이름·주소가 같아요 (한 장소는 한 줄에)")
        seen.setdefault(key, row.line)
    if errors:
        raise SurveyError(errors)
    return rows


def _category(cell):
    for code, label in Place.Category.choices:
        if cell in (code, label):
            return code
    return None


# ── 3. 주소 → 좌표 (카카오 로컬 API, 서버 전용 REST 키) ─────────


def geocode_address(address):
    """주소 → (위도, 경도). 위도·경도 칸을 비워 두면 새 장소에 한해 이걸로 찾는다"""
    key = settings.KAKAO_REST_API_KEY
    if not key:
        raise ValueError("위도·경도가 비어 있어요. 주소로 찾으려면 .env에 KAKAO_REST_API_KEY가 필요해요")
    try:
        res = requests.get(KAKAO_ADDRESS_URL, params={"query": address},
                           headers={"Authorization": f"KakaoAK {key}"}, timeout=5)
    except requests.RequestException as e:
        raise ValueError(f"카카오 주소 검색에 연결하지 못했어요 ({e.__class__.__name__})")
    if res.status_code != 200:
        raise ValueError(f"카카오 주소 검색 실패 (HTTP {res.status_code}). 위도·경도를 직접 적어 주세요")
    documents = res.json().get("documents") or []
    if not documents:
        raise ValueError(f"주소 '{address}'를 찾지 못했어요. 위도·경도를 직접 적어 주세요")
    return Decimal(documents[0]["y"]).quantize(COORD), Decimal(documents[0]["x"]).quantize(COORD)


# ── 4. 저장 ──────────────────────────────────────────────


@dataclass
class ImportResult:
    rows: list = field(default_factory=list)  # [{"line", "name", "status", "judgments": [...]}]
    reports: int = 0

    def count(self, status):
        return sum(1 for r in self.rows if r["status"] == status)


def _find_place(region, row):
    return Place.objects.filter(region=region, name=row.info["이름"], address=row.info.get("주소", "")).first()


def _building_entrance(building):
    entrance = building.entrances.filter(is_main=True).first() or building.entrances.first()
    return entrance or Entrance.objects.create(building=building, name="공용 입구", is_main=True)


def _target_kwargs(target):
    for model, name in ((Entrance, "entrance"), (Building, "building"), (Place, "place")):
        if isinstance(target, model):
            return {name: target}
    raise TypeError(type(target).__name__)


def _already_recorded(target, values, observed_at):
    """값이 모두 지금과 같고, 같은 날이나 그 뒤에 확인한 기록이 이미 있으면 다시 넣지 않는다"""
    latest = (Report.objects.filter(status=Report.Status.VERIFIED, **_target_kwargs(target))
              .order_by("-observed_at").first())
    if latest is None or latest.observed_at.date() < observed_at.date():
        return False
    current = current_values(target)
    return all(key in current and current[key].value == value for key, value in values.items())


def _photo_file(path):
    """방향 바로잡기 + 크기 줄이기. 다시 저장하면서 EXIF(촬영 위치 등)도 지워진다"""
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im)
        im.thumbnail((PHOTO_MAX_PX, PHOTO_MAX_PX))
        buffer = io.BytesIO()
        im.convert("RGB").save(buffer, "JPEG", quality=85)
    return ContentFile(buffer.getvalue(), name=f"{path.stem}.jpg")


def _record(target, values, row, user, result, touched, photo_path=None):
    """대상 하나의 답사 값을 '팀 답사' 제보로 저장. 새로 저장했으면 True"""
    if not values and photo_path is None:
        return False
    observed_at = observed_at_for(row.observed_on)
    if _already_recorded(target, values, observed_at):
        return False
    note = " · ".join(filter(None, [
        f"답사: {row.info['답사자']}" if row.info.get("답사자") else "팀 답사 CSV", row.info.get("메모", ""),
    ]))[:500]
    report = _survey_report(user, observed_at, note, **_target_kwargs(target))
    if photo_path is not None:
        photo = _photo_file(photo_path)
        report.photo.save(photo.name, photo, save=True)
    _save_values(report, values)
    result.reports += 1
    touched.update(affected_places(report))
    return True


def _save_building(region, row, lat, lng):
    info = row.info
    address = info.get("건물 주소") or info.get("주소", "")
    building = Building.objects.filter(region=region, address=address).first()
    if building is None:
        building = Building.objects.create(region=region, address=address, name=info.get("건물 이름", ""),
                                           lat=lat, lng=lng)
    elif info.get("건물 이름") and building.name != info["건물 이름"]:
        building.name = info["건물 이름"]
        building.save(update_fields=["name", "updated_at"])
    return building


def _save_place(region, row, geocode):
    """장소를 찾거나 만든다. 이미 있으면 CSV에 적힌 칸만 고친다 (빈 칸은 그대로)"""
    info = row.info
    place = _find_place(region, row)
    status = "갱신" if place else "새 장소"
    lat, lng = row.lat, row.lng
    if place is None:
        if lat is None:
            lat, lng = geocode(info.get("주소", ""))
        place = Place(region=region, name=info["이름"], address=info.get("주소", ""), lat=lat, lng=lng)
    elif lat is not None:
        place.lat, place.lng = lat, lng
    if info.get("유형"):
        place.category = _category(info["유형"])
    if info.get("층"):
        place.floor = int(info["층"])
    if info.get("전화번호"):
        place.phone = info["전화번호"]
    if "건물 주소" in info or "건물 이름" in info:
        place.building = _save_building(region, row, place.lat, place.lng)
    place.save()
    return place, status


def import_survey(path, *, region=None, photos_dir=None, user=None, dry_run=False, geocode=geocode_address):
    """
    답사 CSV를 넣는다. dry_run=True면 끝까지 해 본 뒤 되돌린다 (판정 결과 미리 보기).
    반환: ImportResult. 문제가 있으면 SurveyError (아무것도 저장 안 됨)
    """
    region = region or Region.objects.filter(is_active=True).order_by("id").first()
    rows = read_survey(path, photos_dir)
    result = ImportResult()
    errors = []
    with transaction.atomic():
        for row in rows:
            try:
                place, status = _save_place(region, row, geocode)
            except ValueError as e:  # 주소 → 좌표 실패
                errors.append(f"{row.line}번째 줄: {e}")
                continue
            touched = {place}
            saved = _record(main_entrance(place), row.values.get("entrance", {}), row, user, result, touched,
                            photo_path=None if dry_run else row.photo_path)
            saved |= _record(place, row.values.get("place", {}), row, user, result, touched)
            if place.building_id:
                saved |= _record(_building_entrance(place.building), row.values.get("building_entrance", {}),
                                 row, user, result, touched)
                saved |= _record(place.building, row.values.get("building", {}), row, user, result, touched)
            for p in touched:
                recompute_place(p)
            if status == "갱신" and not saved:
                status = "변경 없음"
            result.rows.append({"line": row.line, "name": place.name, "status": status, "place": place})
        if errors:
            raise SurveyError(errors)  # 예외로 빠져나가면 transaction.atomic이 전부 되돌린다
        # 판정은 같은 건물의 다른 가게 때문에 바뀔 수 있어서 마지막에 모아서 읽는다
        for r in result.rows:
            r["judgments"] = [
                (j.profile.label, display(j.result)["label"], j.reason)
                for j in r.pop("place").judgments.select_related("profile").order_by("profile__order")
            ]
        if dry_run:
            transaction.set_rollback(True)
    return result
