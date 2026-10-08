from unittest.mock import patch
from django.test import TestCase
from django.urls import reverse
from .boundaries import _wolgye_boundary, _wolgye_layers, region_boundary, region_boundary_layers
from .tests import make_region


class BoundaryTests(TestCase):
    def test_wolgye_boundary_ships_without_db_migration(self):
        region = make_region("wolgye1")
        result = self.client.get(reverse("api:meta")).json()["region"]
        feature = result["boundary"]
        self.assertEqual(feature["properties"]["adm_nm"], "서울특별시 노원구 월계1동")
        self.assertEqual(feature["properties"]["boundary_date"], "2026-07-01")
        self.assertIn("SGIS", feature["properties"]["attribution"])
        self.assertIn("CC BY 4.0", feature["properties"]["license"])
        self.assertEqual(feature["geometry"]["type"], "MultiPolygon")
        region.refresh_from_db(); self.assertIsNone(region.boundary)

    def test_configured_boundary_takes_priority_and_other_region_never_uses_wolgye(self):
        configured={"type":"Polygon","coordinates":[[[127,37],[128,37],[128,38],[127,37]]]}
        region=make_region("wolgye1")
        region.boundary = configured
        region.save(update_fields=["boundary"])
        self.assertEqual(region_boundary(region), configured)
        self.assertIsNone(region_boundary(make_region("other")))

    def test_unreadable_or_corrupt_file_does_not_break_meta(self):
        region=make_region("wolgye1")
        for error in (OSError(), ValueError()):
            _wolgye_boundary.cache_clear()
            with patch("places.boundaries.Path.read_text", side_effect=error):
                self.assertIsNone(region_boundary(region))
        _wolgye_boundary.cache_clear()

    def test_layers_keep_legacy_boundary_and_identify_three_districts(self):
        region = make_region("wolgye1")
        data = self.client.get(reverse("api:meta")).json()["region"]
        layers = data["boundary_layers"]
        self.assertEqual(data["boundary"], region_boundary(region))
        self.assertEqual(layers["detail_max_level"], 5)
        features = layers["districts"]["features"]
        self.assertEqual([f["properties"]["adm_cd2"] for f in features], ["1135056000", "1135057000", "1135058000"])
        self.assertEqual([f["properties"]["display_color"] for f in features], ["#d14343", "#245ccc", "#16804a"])
        self.assertEqual(features[0]["geometry"], data["boundary"]["geometry"])
        for feature in features + [layers["overview"]]:
            self.assertEqual(feature["properties"]["boundary_date"], "2026-07-01")
            self.assertIn("SGIS", feature["properties"]["attribution"])
        self.assertEqual(layers["overview"]["geometry"]["type"], "Polygon")
        self.assertEqual(len(layers["overview"]["geometry"]["coordinates"]), 1)
        region.refresh_from_db(); self.assertIsNone(region.boundary)

    def test_layers_do_not_override_custom_or_other_region(self):
        region = make_region("wolgye1")
        region.boundary = {"type": "Polygon", "coordinates": []}
        self.assertIsNone(region_boundary_layers(region))
        self.assertIsNone(region_boundary_layers(make_region("other")))

    def test_missing_layer_files_leave_legacy_boundary_available(self):
        region = make_region("wolgye1")
        for error in (OSError(), ValueError()):
            _wolgye_layers.cache_clear()
            with patch("places.boundaries.Path.read_text", side_effect=error):
                self.assertIsNone(region_boundary_layers(region))
        _wolgye_layers.cache_clear()
        self.assertIsNotNone(region_boundary(region))

    def test_map_has_district_toggle_and_text_legend(self):
        make_region("wolgye1")
        response = self.client.get(reverse("places:map"))
        self.assertContains(response, "동별 구역 표시")
        self.assertContains(response, 'id="boundary-legend"')
