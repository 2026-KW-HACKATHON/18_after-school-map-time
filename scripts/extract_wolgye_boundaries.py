"""고정 원자료에서 월계 세 동과 합쳐진 외곽 추출 (생성 도구에만 Shapely 2.1.2 필요)."""
import json
import sys
from pathlib import Path

from shapely.geometry import mapping, shape
from shapely.ops import unary_union


def extract(source_path, output_dir):
    source = json.loads(Path(source_path).read_text(encoding="utf-8"))
    output = Path(output_dir)
    original = json.loads((output / "wolgye1.geojson").read_text(encoding="utf-8"))
    codes = ("1135056000", "1135057000", "1135058000")
    # 빨간색은 쓰지 않는다 (기획 v2: 빨강은 "위험·금지"로 읽혀 낙인이 됨) → 월계1동은 보라
    colors = ("#7b4fc9", "#245ccc", "#16804a")
    features = []
    for number, (code, color) in enumerate(zip(codes, colors), 1):
        matches = [f for f in source["features"] if f["properties"]["adm_cd2"] == code]
        if len(matches) != 1:
            raise ValueError(f"월계{number}동 원자료가 유일하지 않습니다.")
        feature = matches[0]
        if feature["properties"]["adm_nm"] != f"서울특별시 노원구 월계{number}동":
            raise ValueError("행정동 이름/코드가 다릅니다.")
        feature["properties"].update({key: original["properties"][key] for key in
            ("source_url", "boundary_date", "license", "attribution")})
        feature["properties"].update(display_name=f"월계{number}동", display_color=color)
        if not shape(feature["geometry"]).is_valid:
            raise ValueError("유효하지 않은 경계입니다.")
        features.append(feature)
    if features[0]["geometry"] != original["geometry"]:
        raise ValueError("기존 월계1동과 원자료 좌표가 다릅니다.")
    combined = unary_union([shape(f["geometry"]) for f in features])
    if not combined.is_valid or combined.geom_type != "Polygon":
        raise ValueError("세 동의 외곽이 연속된 Polygon이 아닙니다.")
    overview = {"type": "Feature", "properties": {
        key: original["properties"][key] for key in ("source_url", "boundary_date", "license", "attribution")
    }, "geometry": mapping(combined)}
    overview["properties"].update(display_name="월계1·2·3동 전체", combined_from=list(codes),
                                  processing="세 행정동의 기하학적 합집합; 내부 공유 경계 제거")
    for filename, value in (("wolgye-districts.geojson", {"type": "FeatureCollection", "features": features}),
                            ("wolgye.geojson", overview)):
        (output / filename).write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print("월계1·2·3동 좌표 보존 및 합쳐진 외곽 생성 완료")


if __name__ == "__main__":
    extract(*sys.argv[1:])
