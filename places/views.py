from django.shortcuts import get_object_or_404, render

from .models import Place, Region
from .selectors import place_detail


def map_page(request):
    region = Region.objects.filter(is_active=True).order_by("id").first()
    return render(request, "places/map.html", {"region": region})


def detail_page(request, pk):
    place = get_object_or_404(Place.objects.select_related("building", "region"), pk=pk, is_closed=False)
    return render(request, "places/detail.html", place_detail(place))
