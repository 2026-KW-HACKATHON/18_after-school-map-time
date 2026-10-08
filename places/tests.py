from decimal import Decimal
from io import StringIO

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase

from .models import Building, Entrance, FieldDefinition, Place, Region


def make_region(code="wolgye1"):
    return Region.objects.create(code=code, name=code, center_lat=Decimal("37.62"), center_lng=Decimal("127.05"))


def make_place(region, name="가게", **kwargs):
    return Place.objects.create(region=region, name=name, lat=Decimal("37.62"), lng=Decimal("127.05"), **kwargs)


class EntranceConstraintTests(TestCase):
    def setUp(self):
        self.region = make_region()
        self.place = make_place(self.region)
        self.building = Building.objects.create(
            region=self.region, address="월계동 1", lat=Decimal("37.62"), lng=Decimal("127.05")
        )

    def test_place_or_building_entrance_ok(self):
        Entrance.objects.create(place=self.place)
        Entrance.objects.create(building=self.building)

    def test_entrance_needs_exactly_one_owner(self):
        for kwargs in ({}, {"place": self.place, "building": self.building}):
            with self.subTest(kwargs=kwargs), self.assertRaises(IntegrityError), transaction.atomic():
                Entrance.objects.create(**kwargs)


class RegionScopeTests(TestCase):
    def test_in_region_by_object_or_code(self):
        wolgye, other = make_region("wolgye1"), make_region("gongneung")
        mine = make_place(wolgye, "월계 가게")
        make_place(other, "공릉 가게")
        self.assertEqual(list(Place.objects.in_region(wolgye)), [mine])
        self.assertEqual(list(Place.objects.in_region("wolgye1")), [mine])

    def test_place_and_building_region_must_match(self):
        wolgye, other = make_region("wolgye1"), make_region("gongneung")
        building = Building.objects.create(region=other, address="공릉동 1", lat=Decimal("37.62"), lng=Decimal("127.05"))
        place = Place(region=wolgye, building=building, name="가게", lat=Decimal("37.62"), lng=Decimal("127.05"))
        with self.assertRaises(ValidationError):
            place.clean()


class SeedBaseTests(TestCase):
    def test_seed_is_idempotent(self):
        call_command("seed_base", stdout=StringIO())
        first = (Region.objects.count(), FieldDefinition.objects.count())
        call_command("seed_base", stdout=StringIO())
        self.assertEqual((Region.objects.count(), FieldDefinition.objects.count()), first)
        self.assertTrue(Region.objects.filter(code="wolgye1").exists())
        step = FieldDefinition.objects.get(key="step_height_cm")
        self.assertEqual((step.scope, step.value_type, step.unit), ("ENTRANCE", "NUMBER", "cm"))
