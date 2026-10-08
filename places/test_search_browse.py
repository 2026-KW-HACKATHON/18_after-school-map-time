"""검색어 없는 전체 탐색도 서비스 지역·폐업·업종·개인화 정책을 유지한다."""
from django.core.cache import cache
from django.urls import reverse
from judgments.mobility import default_settings
from .test_views import ViewTestBase
from .tests import make_place, make_region


class SearchBrowseTests(ViewTestBase):
    url = reverse("places:search")

    def setUp(self):
        super().setUp()
        cache.clear()

    def personal(self, **options):
        return self.client.post(reverse("api:mobility-evaluate"),
                                {"settings": default_settings(), "q": "", **options}, content_type="application/json")

    def test_empty_and_whitespace_show_same_scoped_places(self):
        make_place(self.region, "폐업", is_closed=True)
        make_place(make_region("other"), "다른 지역")
        for q in ("", "   ", "\t"):
            with self.subTest(q=q):
                response = self.client.get(self.url, {"q": q})
                ids = [row["place"].pk for row in response.context["results"]]
                self.assertEqual(set(ids), {self.easy.pk, self.hard.pk, self.unknown.pk})
                personal = self.personal(q=q)
                self.assertEqual(personal.status_code, 200)
                self.assertEqual([row["id"] for row in personal.json()["results"]], ids)

    def test_more_than_30_are_all_reachable_with_matching_personal_pages(self):
        for i in range(35): make_place(self.region, f"테스트 {i:02}")
        all_ids = []
        for page in (1, 2):
            response = self.client.get(self.url, {"page": page, "profile": "CRUTCH"})
            ids = [row["place"].pk for row in response.context["results"]]
            data = self.personal(page=page).json()
            self.assertEqual([row["id"] for row in data["results"]], ids)
            self.assertEqual(data["total_count"], 38)
            self.assertEqual(data["page"], page)
            self.assertEqual(data["num_pages"], 2)
            self.assertEqual(data["has_next"], page == 1)
            self.assertEqual(data["has_previous"], page == 2)
            self.assertContains(response, "장소 목록 페이지")
            self.assertIn("profile=CRUTCH", response.context["pagination_query"])
            all_ids.extend(ids)
        self.assertEqual(len(all_ids), 38)
        self.assertEqual(len(set(all_ids)), 38)

    def test_empty_query_category_filters_and_empty_state(self):
        self.easy.category = "CAFE"; self.easy.save()
        for category, expected in (("CAFE", [self.easy.pk]), ("PHARMACY", None), ("RESTAURANT", [])):
            response=self.client.get(self.url, {"category":category})
            ids=[row["place"].pk for row in response.context["results"]]
            # An unsupported category is reset to the existing all-category policy.
            if expected is None:
                self.assertEqual(len(ids), 3)
            else:
                self.assertEqual(ids, expected)
            if expected == []:
                self.assertContains(response,"아직 등록된 장소가 없어요")
                self.assertNotContains(response,'""(으)로')
            if expected is not None:
                self.assertEqual([row["id"] for row in self.personal(category=category).json()["results"]], ids)

    def test_invalid_api_page_is_400_and_large_valid_page_uses_last(self):
        for page in ("²", "１", "", "-1", " 1", True, [], None, "9" * 80):
            with self.subTest(page=page): self.assertEqual(self.personal(page=page).status_code, 400)
        self.assertEqual(self.personal(page=99999).json()["page"], 1)
        self.assertEqual(self.client.get(self.url, {"page":"²"}).status_code, 200)

    def test_pagination_preserves_query_category_and_profile(self):
        for i in range(35): make_place(self.region, f"주소검증 {i:02}", category="CAFE")
        response=self.client.get(self.url, {"q":"주소검증","category":"CAFE","profile":"STROLLER","page":2})
        self.assertEqual(len(response.context["results"]),5)
        self.assertEqual(self.personal(q="주소검증",category="CAFE",page="2").json()["count"],5)
        self.assertIn("category=CAFE",response.context["pagination_query"])
        self.assertIn("profile=STROLLER",response.context["pagination_query"])

    def test_no_region_is_explained_and_api_scope_rejected(self):
        self.region.is_active=False;self.region.save()
        self.assertContains(self.client.get(self.url),"아직 서비스 지역이 등록되지 않았어요")
        self.assertEqual(self.personal().status_code,404)

    def test_page_option_does_not_change_map_evaluation(self):
        response=self.client.post(reverse("api:mobility-evaluate"),
                                  {"settings":default_settings(),"page":1},content_type="application/json")
        self.assertEqual(response.status_code,400)
        response=self.client.post(reverse("api:mobility-evaluate"),
                                  {"settings":default_settings()},content_type="application/json")
        self.assertEqual(response.status_code,200)
        self.assertNotIn("page",response.json())
