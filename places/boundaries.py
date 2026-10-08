"""지역 경계는 기존 DB 설정 우선. 월계1동은 출처를 보존한 배포 파일로 폴백."""
import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def _wolgye_boundary():
    try:
        return json.loads((Path(__file__).parent / "data/wolgye1.geojson").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def region_boundary(region):
    if region.boundary is not None:
        return region.boundary
    return _wolgye_boundary() if region.code == "wolgye1" else None
