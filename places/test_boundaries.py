from unittest.mock import patch
from django.test import TestCase
from django.urls import reverse
from .boundaries import _wolgye_boundary, region_boundary
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
