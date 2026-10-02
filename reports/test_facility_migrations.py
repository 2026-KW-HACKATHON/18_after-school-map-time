"""기존 입구 제보와 관측값이 확장 Migration 이후에도 보존되는지 확인한다."""

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class FacilityMigrationTests(TransactionTestCase):
    def test_existing_entrance_report_and_values_survive_additive_migrations(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        before = [("places", "0001_initial"), ("reports", "0005_public_data_source")]
        try:
            executor.migrate(before)
            apps = executor.loader.project_state(before).apps
            Region = apps.get_model("places", "Region")
            Place = apps.get_model("places", "Place")
            Entrance = apps.get_model("places", "Entrance")
            Field = apps.get_model("places", "FieldDefinition")
            Report = apps.get_model("reports", "Report")
            Value = apps.get_model("reports", "AccessibilityValue")
            region = Region.objects.create(code="old", name="기존 지역", center_lat="37.62", center_lng="127.05")
            place = Place.objects.create(region=region, name="기존 가게", lat="37.62", lng="127.05")
            entrance = Entrance.objects.create(place=place, name="기존 정문", is_main=True)
            field = Field.objects.create(key="step_height_cm", label="입구 단차", scope="ENTRANCE", value_type="NUMBER")
            checked = timezone.now()
            report = Report.objects.create(entrance=entrance, source="USER_REPORT", status="VERIFIED",
                photo="reports/existing.jpg", note="기존 설명", observed_at=checked,
                profiles=["WHEELCHAIR"], suggested_phone="02-123-4567")
            value = Value.objects.create(report=report, field=field, value_number=3)
            ids = report.pk, value.pk, entrance.pk
            executor = MigrationExecutor(connection)
            executor.migrate(latest)
            apps = executor.loader.project_state(latest).apps
            migrated = apps.get_model("reports", "Report").objects.get(pk=ids[0])
            self.assertEqual(migrated.entrance_id, ids[2])
            self.assertEqual(migrated.status, "VERIFIED")
            self.assertEqual(migrated.photo.name, "reports/existing.jpg")
            self.assertEqual(migrated.note, "기존 설명")
            self.assertEqual(migrated.profiles, ["WHEELCHAIR"])
            self.assertEqual(migrated.observed_at, checked)
            self.assertEqual(migrated.suggested_phone, "02-123-4567")
            self.assertEqual(migrated.facility_kind, "")
            self.assertIsNone(migrated.facility_id)
            self.assertEqual(apps.get_model("reports", "AccessibilityValue").objects.get(pk=ids[1]).value_number, 3)
            self.assertFalse(apps.get_model("places", "AccessFacility").objects.exists())
            self.assertTrue(apps.get_model("places", "FieldDefinition").objects.filter(key="facility_available").exists())
        finally:
            MigrationExecutor(connection).migrate(latest)
