"""새 설정 테이블 UP과 기존 데이터 보존을 Django가 만든 test DB에서만 확인한다."""
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

from places.models import Entrance
from places.tests import make_place, make_region
from reports.models import Report


class MobilityMigrationTests(TransactionTestCase):
    def test_additive_migration_preserves_users_places_entrances_and_reports(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        try:
            executor.migrate([("accounts", "0002_notification")])
            old_apps = executor.loader.project_state([("accounts", "0002_notification")]).apps
            user = old_apps.get_model("accounts", "User").objects.create(username="before-mobility", nickname="기존 회원")
            region = make_region("migration-mobility")
            place = make_place(region, "기존 장소")
            entrance = Entrance.objects.create(place=place, name="기존 입구")
            report = Report.objects.create(entrance=entrance, created_by_id=user.pk, note="기존 제보")
            executor = MigrationExecutor(connection)
            executor.migrate([("accounts", "0003_mobilitypreference")])
            new_apps = executor.loader.project_state([("accounts", "0003_mobilitypreference")]).apps
            self.assertEqual(new_apps.get_model("accounts", "User").objects.get(pk=user.pk).nickname, "기존 회원")
            self.assertEqual(Report.objects.get(pk=report.pk).note, "기존 제보")
            self.assertEqual(Entrance.objects.get(pk=entrance.pk).place_id, place.pk)
            preference = new_apps.get_model("accounts", "MobilityPreference")
            self.assertFalse(preference.objects.exists())
            preference.objects.create(user_id=user.pk, data={"version": 1})
            self.assertEqual(preference.objects.get(user_id=user.pk).data, {"version": 1})
        finally:
            MigrationExecutor(connection).migrate(latest)
