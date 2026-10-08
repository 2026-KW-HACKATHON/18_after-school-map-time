"""
공공데이터 가져오기 (Could "노원구 공공데이터 연동").

출처: 공공데이터포털 '한국사회보장정보원_장애인편의시설 현황' (B554287/DisabledPersonConvenientFacility)
  1. getDisConvFaclList  — 시·군·구 안 편의시설 대상 시설 목록 (시설명, 주소, 위·경도, 시설 종류, 시설ID)
  2. getFacInfoOpenApiJpEvalInfoList — 시설 하나의 '설치된 편의시설 항목' (예: 승강기, 주출입구 높이차이 제거)

이 데이터는 편의시설 설치 의무가 있는 공공기관·큰 건물 위주라 동네 작은 가게는 거의 없다 → 팀 답사를 보강하는 용도.
항목은 '있다'만 알려 주므로, 우리 측정 항목과 뜻이 바로 맞는 것만 값으로 옮긴다 (FIELD_MAP).
문 폭처럼 수치가 없는 항목은 비워 둔다 — 지어낸 값으로 판정하지 않기 위해.

호출 수: 개발 계정은 기능별 하루 100회. 목록 1~2회 + 시설마다 1회 → --cache 로 받은 내용을 파일에 저장해 다시 씀.
"""

import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from pathlib import Path

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from judgments.constants import display
from judgments.engine import recompute_place
from reports.models import AccessibilityValue, Report

from .geocoding import geocode
from .models import Building, Entrance, Place

BASE_URL = "https://apis.data.go.kr/B554287/DisabledPersonConvenientFacility/"
LIST_PAGE_SIZE = 600

# 공공데이터 항목 → (우리 필드 대상, 필드 키, 값). 뜻이 바로 맞는 것만. 바꾸려면 여기만 고친다
FIELD_MAP = {
    "주출입구 높이차이 제거": ("entrance", "step_height_cm", 0),   # 턱을 없애거나 경사로 등으로 높이차를 없앤 출입구
    "승강기": ("building", "elevator", True),
    "장애인사용가능화장실": ("place", "accessible_toilet", True),
}

# 주거시설·대피소는 "가게에 들어갈 수 있나"와 상관없어 가져오지 않는다 (시설 종류 이름에 이 글자가 있으면 제외)
EXCLUDED_TYPE_WORDS = ("주택", "아파트", "기숙사", "대피소", "부대복리")

# 시설 종류 → 장소 유형 (글자가 들어 있으면 그 유형, 없으면 기타)
CATEGORY_WORDS = [
    (("음식점",), Place.Category.RESTAURANT),
    (("수퍼마켓", "소매점", "소매시장", "도매시"), Place.Category.STORE),
    (("약국",), Place.Category.PHARMACY),
    (("의원", "병원", "보건소"), Place.Category.CLINIC),
    (("자치센터", "우체국", "청사", "파출소", "지구대", "도서관", "공중화장실", "체육관", "경로당"), Place.Category.PUBLIC),
]


class PublicDataError(Exception):
    pass


# ── 1. 받아 오기 ─────────────────────────────────────────


def _call(operation, **params):
    key = settings.PUBLIC_DATA_API_KEY
    if not key:
        raise PublicDataError("PUBLIC_DATA_API_KEY 가 .env에 없어요 (공공데이터포털 일반 인증키)")
    try:
        res = requests.get(BASE_URL + operation, params={"serviceKey": key, **params}, timeout=30)
    except requests.RequestException as e:
        raise PublicDataError(f"공공데이터포털에 연결하지 못했어요 ({e.__class__.__name__})")
    if res.status_code != 200:
        raise PublicDataError(f"공공데이터포털 응답 오류 (HTTP {res.status_code})")
    try:
        root = ET.fromstring(res.content)
    except ET.ParseError:
        raise PublicDataError("공공데이터포털 응답을 읽을 수 없어요 (인증키가 맞는지, 하루 호출 수를 넘지 않았는지 확인)")
    code = root.findtext("resultCode")
    if code not in (None, "0", "00"):
        raise PublicDataError(f"공공데이터포털 오류: {root.findtext('resultMessage') or code}")
    return root


def fetch_list(sido, sigungu):
    """시·군·구 안 시설 목록 [dict]"""
    rows, page = [], 1
    while True:
        root = _call("getDisConvFaclList", pageNo=page, numOfRows=LIST_PAGE_SIZE, siDoNm=sido, cggNm=sigungu)
        batch = [{c.tag: (c.text or "").strip() for c in item} for item in root.iter("servList")]
        rows += batch
        total = int(root.findtext("totalCount") or 0)
        if not batch or len(rows) >= total:
            return rows
        page += 1


def fetch_items(facility_id):
    """시설 하나에 설치된 편의시설 항목 ['승강기', ...]"""
    root = _call("getFacInfoOpenApiJpEvalInfoList", wfcltId=facility_id)
    text = root.findtext("servList/evalInfo") or ""
    return [item.strip() for item in text.split(",") if item.strip()]


def select_facilities(rows, dong_code):
    """법정동 코드(시설ID 앞 10자리)로 고르고, 영업 중·주거시설 아닌 곳만, 같은 시설ID는 하나만"""
    picked = {}
    for row in rows:
        fid = row.get("wfcltId", "")
        if not fid.startswith(dong_code) or row.get("salStaDivCd", "Y") != "Y":
            continue
        if any(word in row.get("faclTyCd", "") for word in EXCLUDED_TYPE_WORDS):
            continue
        picked.setdefault(fid, row)
    return list(picked.values())


def load_or_fetch(cache_path, sido, sigungu, dong_code, limit, already_imported):
    """
    --cache 파일이 있으면 그대로 쓰고(호출 0회), 없으면 받아서 저장한다.
    반환: [{"row": 목록 한 줄, "items": [항목]}], 호출 수
    """
    if cache_path and Path(cache_path).exists():
        return json.loads(Path(cache_path).read_text(encoding="utf-8")), 0
    rows = select_facilities(fetch_list(sido, sigungu), dong_code)
    calls = (len(rows) + LIST_PAGE_SIZE - 1) // LIST_PAGE_SIZE or 1
    data = []
    for row in rows:
        if row["wfcltId"] in already_imported:
            continue  # 이미 가져온 시설은 항목을 다시 부르지 않음 (하루 호출 수 아끼기)
        if calls >= limit:
            break
        data.append({"row": row, "items": fetch_items(row["wfcltId"])})
        calls += 1
    if cache_path:
        Path(cache_path).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data, calls


# ── 2. 넣기 ─────────────────────────────────────────────


@dataclass
class ImportRow:
    name: str
    status: str                      # 새 장소 / 갱신 / 변경 없음 / 건너뜀
    note: str = ""
    judgments: list = field(default_factory=list)


def _category(type_name):
    for words, category in CATEGORY_WORDS:
        if any(word in type_name for word in words):
            return category
    return Place.Category.ETC


def display_name(row):
    """시설명이 시설 종류와 같으면(예: '일반음식점') 구분이 안 되므로 '일반음식점 (석계로1길 18)'처럼 주소를 붙인다"""
    name, kind, address = row.get("faclNm", "").strip(), row.get("faclTyCd", "").strip(), row.get("lcMnad", "")
    if name and name != kind:
        return name
    street = " ".join(address.split()[-2:]) if address else ""
    return f"{kind or '시설'} ({street})" if street else (kind or "이름 없는 시설")


def _distance_m(lat1, lng1, lat2, lng2):
    """두 좌표 사이 거리(미터) — 동네 범위라 평면 근사로 충분"""
    import math

    dy = (float(lat1) - float(lat2)) * 111_000
    dx = (float(lng1) - float(lng2)) * 111_000 * math.cos(math.radians(float(lat2)))
    return math.hypot(dx, dy)


def _coord(value):
    try:
        number = Decimal(value)
    except (InvalidOperation, TypeError):
        return None
    return number.quantize(Decimal("0.000001")) if number else None  # 0 은 '좌표 없음'


def _observed_at(estb):
    """공공데이터 등록일(estbDate, YYYYMMDD) 정오. 없으면 지금 — 이후 답사·제보가 더 최신이면 그 값이 우선"""
    try:
        day = datetime.strptime(estb, "%Y%m%d").date()
    except (TypeError, ValueError):
        return timezone.now()
    return timezone.make_aware(datetime.combine(min(day, date.today()), time(12, 0)))


def imported_ids():
    """이미 가져온 시설ID (기록 설명에 'ID:' 로 남김)"""
    notes = Report.objects.filter(source=Report.Source.PUBLIC_DATA).values_list("note", flat=True)
    return {n.split("ID:")[1].split()[0] for n in notes if "ID:" in n}


def _record(target_kw, values, observed_at, note):
    report = Report.objects.create(source=Report.Source.PUBLIC_DATA, status=Report.Status.VERIFIED,
                                   observed_at=observed_at, note=note, **target_kw)
    for key, raw in values.items():
        value = AccessibilityValue(report=report, field_id=key)
        value.set_value(raw)
        value.full_clean()
        value.save()


def import_facilities(data, region, dry_run=False, radius_m=None):
    """radius_m: 지역 중심에서 이 거리(미터) 밖 시설은 건너뜀 (없으면 법정동 전체)"""
    done = imported_ids()
    rows = []
    with transaction.atomic():
        for entry in data:
            row = entry["row"]
            items = list(dict.fromkeys(entry["items"]))  # 같은 항목이 두 번 오는 경우가 있어 순서 유지하며 중복 제거
            fid, name, address = row["wfcltId"], display_name(row), row.get("lcMnad", "")
            if fid in done:
                rows.append(ImportRow(name, "변경 없음", "이미 가져옴"))
                continue
            lat, lng = _coord(row.get("faclLat")), _coord(row.get("faclLng"))
            located = ""
            if lat is None or lng is None:
                try:
                    found = geocode(address, near=(region.center_lat, region.center_lng))
                except ValueError as e:
                    rows.append(ImportRow(name, "건너뜀", f"위치를 찾지 못함: {e}"))
                    continue
                lat, lng, located = found.lat, found.lng, f"주소로 위치 찾음: {found.label}"
            if radius_m and _distance_m(lat, lng, region.center_lat, region.center_lng) > radius_m:
                rows.append(ImportRow(name, "건너뜀", f"지역 중심에서 {radius_m}m 밖"))
                continue

            values = {"entrance": {}, "place": {}, "building": {}}
            for item in items:
                if item in FIELD_MAP:
                    scope, key, value = FIELD_MAP[item]
                    values[scope][key] = value

            place = Place.objects.filter(region=region, name=name, address=address).first()
            status = "갱신" if place else "새 장소"
            if place is None:
                place = Place.objects.create(region=region, name=name, address=address, lat=lat, lng=lng,
                                             category=_category(row.get("faclTyCd", "")))
            if values["building"] and not place.building_id:
                building = Building.objects.filter(region=region, address=address).first() or Building.objects.create(
                    region=region, name=name, address=address, lat=lat, lng=lng)
                place.building = building
                place.save(update_fields=["building", "updated_at"])

            observed_at = _observed_at(row.get("estbDate"))
            note = f"공공데이터 장애인편의시설 현황 ID:{fid} · 항목: {', '.join(items) or '없음'}"[:500]
            entrance = place.entrances.order_by("-is_main", "id").first() or Entrance.objects.create(
                place=place, name="주출입구", is_main=True)
            _record({"entrance": entrance}, values["entrance"], observed_at, note)  # 항목이 없어도 ID 기록용으로 남김
            if values["place"]:
                _record({"place": place}, values["place"], observed_at, note)
            if values["building"]:
                _record({"building": place.building}, values["building"], observed_at, note)
            recompute_place(place)
            judgments = [(j.profile.label, display(j.result)["label"])
                         for j in place.judgments.select_related("profile").order_by("profile__order")]
            rows.append(ImportRow(name, status, located, judgments))
        if dry_run:
            transaction.set_rollback(True)
    return rows
