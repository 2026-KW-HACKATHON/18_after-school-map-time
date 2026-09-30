"""사장님 화면 (기획 v2 4장). 인증된 사장님만 자기 가게 화면에 들어올 수 있다."""

from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from judgments.models import ConditionProfile
from places.models import Building, FieldDefinition, Place, Region
from places.selectors import building_common_section

from . import services
from .forms import ClaimForm, CorrectionForm, DeclarationForm, PhotoRequestForm, ResponseForm
from .models import OwnerClaim, OwnerResponse, SupportProgram


def owner_required(view):
    """URL의 장소(pk)에 대해 승인된 사장님만 (관리자도 도와주기 위해 허용)"""

    @login_required
    @wraps(view)
    def wrapper(request, pk, *args, **kwargs):
        place = get_object_or_404(Place, pk=pk)
        if not (request.user.is_staff or OwnerClaim.is_owner(request.user, place)):
            messages.error(request, "이 가게의 사장님 인증이 필요해요.")
            return redirect("owners:home")
        return view(request, place, *args, **kwargs)

    return wrapper


def building_owner_required(view):
    """URL의 건물(pk)에 대해 승인된 건물주만 (관리자도 허용)"""

    @login_required
    @wraps(view)
    def wrapper(request, pk, *args, **kwargs):
        building = get_object_or_404(Building, pk=pk)
        if not (request.user.is_staff or OwnerClaim.is_building_owner(request.user, building)):
            messages.error(request, "이 건물의 건물주 인증이 필요해요.")
            return redirect("owners:home")
        return view(request, building, *args, **kwargs)

    return wrapper


def claim(request):
    """
    인증 코드 입력 (기획 v2 4.1). 식별번호는 받지 않는다.
    로그인 전에도 안내는 보이고(무엇을 하는 곳인지 먼저 알 수 있게), 신청할 때만 카카오 로그인.
    안내 쪽지의 주소(?code=123456)로 들어오면 코드가 미리 채워진다.
    """
    code = request.GET.get("code", "")
    form = ClaimForm(request.POST or None, initial={"code": code if code.isdigit() and len(code) == 6 else ""})
    if request.method == "POST" and not request.user.is_authenticated:
        return redirect(f"{reverse('account_login')}?next={request.get_full_path()}")
    if request.method == "POST" and form.is_valid():
        try:
            services.claim_with_code(request.user, form.cleaned_data["code"])
        except services.OwnerError as e:
            form.add_error("code", str(e))
        else:
            messages.success(request, "인증을 신청했어요. 운영진이 확인하면 사장님 화면을 쓸 수 있어요.")
            return redirect("owners:home")
    return render(request, "owners/claim.html", {"form": form})


@login_required
def home(request):
    claims = OwnerClaim.objects.filter(user=request.user).select_related("place", "building")
    return render(request, "owners/home.html", {"claims": claims})


@owner_required
def photo_request(request, place):
    """입구 사진 교체 요청 (기획 v2 4.4) — 운영자가 확인한 뒤 바뀐다"""
    form = PhotoRequestForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            services.submit_photo_request(request.user, place, form.cleaned_data["photo"],
                                          form.cleaned_data["reason"], form.cleaned_data["note"])
        except services.OwnerError as e:
            form.add_error(None, str(e))
        else:
            messages.success(request, "사진 교체를 요청했어요. 운영진이 확인하면 바뀌어요.")
            return redirect("owners:dashboard", pk=place.pk)
    return render(request, "owners/photo_request_form.html", {"form": form, "place": place})


@owner_required
def dashboard(request, place):
    """사장님 대시보드 (기획 v2 4.5): 잠재 손님 숫자, 개선 가이드, 지원사업"""
    return render(request, "owners/dashboard.html", {"place": place, **services.dashboard(place)})


@owner_required
def response_edit(request, place):
    """사장님 한마디·도움 요청 방법 — 안내 문구라 저장하면 바로 공개"""
    instance = OwnerResponse.objects.filter(place=place).first() or OwnerResponse(place=place)
    form = ResponseForm(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        response = form.save(commit=False)
        response.updated_by = request.user
        response.save()
        messages.success(request, "저장했어요. 가게 상세 화면에 바로 보여요.")
        return redirect("owners:dashboard", pk=place.pk)
    return render(request, "owners/response_form.html", {"form": form, "place": place})


@owner_required
def declaration(request, place):
    """도움 제공·이동식 경사로 선언 — 사진 확인 후 판정에 반영 (기획 v2 4.2)"""
    form = DeclarationForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            services.submit_owner_report(request.user, place, form.values(), form.cleaned_data["photo"],
                                         form.cleaned_data["note"])
        except services.OwnerError as e:
            form.add_error(None, str(e))
        else:
            messages.success(request, "접수했어요. 사진이 확인되면 지도에 반영돼요.")
            return redirect("owners:dashboard", pk=place.pk)
    return render(request, "owners/declaration_form.html", {"form": form, "place": place})


@owner_required
def correction(request, place):
    """정정 요청 (기획 v2 4.3). 기존 값은 확인 전까지 그대로, 해당 항목에 '확인 중' 표시"""
    form = CorrectionForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        definition = form.cleaned_data["definition"]
        target = services.main_entrance(place) if definition.scope == FieldDefinition.Scope.ENTRANCE else place
        try:
            services.submit_owner_report(request.user, target, {definition.key: form.cleaned_data["value"].strip()},
                                         form.cleaned_data["photo"], form.cleaned_data["note"])
        except services.OwnerError as e:
            form.add_error("field", str(e))
        else:
            messages.success(request, "정정 요청을 접수했어요. 확인되면 반영되고, 반려되면 사유를 알려드려요.")
            return redirect("owners:dashboard", pk=place.pk)
    return render(request, "owners/correction_form.html", {"form": form, "place": place})


@login_required
@require_POST
def wish_toggle(request, pk):
    """'가고 싶어요' 누르기·취소 (들어가기 어려운 가게에만 버튼이 보임)"""
    place = get_object_or_404(Place, pk=pk, is_closed=False)
    profile = get_object_or_404(ConditionProfile, key=request.POST.get("profile"), is_active=True)
    on = services.toggle_wish(request.user, place, profile)
    messages.success(request, "사장님께 전해져요. 개선되면 지도에서 확인할 수 있어요." if on else "취소했어요.")
    back = request.POST.get("next") or "/"
    if not url_has_allowed_host_and_scheme(back, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        back = "/"
    return redirect(back)


@building_owner_required
def building_dashboard(request, building):
    """건물주 화면 (기획 v2 5.2): 건물 공용 정보, 건물 안 가게 판정, 개선 시뮬레이션"""
    return render(request, "owners/building_dashboard.html", {
        **services.building_overview(building),
        "common": building_common_section(building),
        "my_reports": services.sent_requests(Q(building=building) | Q(entrance__building=building)),
        "share_url": request.build_absolute_uri(reverse("owners:building-improve", args=[building.pk])),
    })


@building_owner_required
def building_correction(request, building):
    """건물주 정정 요청 — 건물 공용 입구·시설 값. 절차는 가게 정정 요청과 같음 (주민 2명 확인 또는 운영자 승인)"""
    form = CorrectionForm(request.POST or None, request.FILES or None, scopes=CorrectionForm.BUILDING_SCOPES)
    if request.method == "POST" and form.is_valid():
        definition = form.cleaned_data["definition"]
        target = (services.building_main_entrance(building) if definition.scope == FieldDefinition.Scope.ENTRANCE
                  else building)
        try:
            services.submit_owner_report(request.user, target, {definition.key: form.cleaned_data["value"].strip()},
                                         form.cleaned_data["photo"], form.cleaned_data["note"])
        except services.OwnerError as e:
            form.add_error("field", str(e))
        else:
            messages.success(request, "정정 요청을 접수했어요. 확인되면 반영되고, 반려되면 사유를 알려드려요.")
            return redirect("owners:building", pk=building.pk)
    return render(request, "owners/correction_form.html", {"form": form, "building": building})


def building_improve(request, pk):
    """
    개선 시뮬레이션 공유 페이지 (기획 v2 5.2, 로그인 없이). 사장님이 건물주에게 보여 줄 수 있게.
    지도에 이미 공개된 정보로만 계산한다.
    """
    building = get_object_or_404(Building, pk=pk)
    return render(request, "owners/building_improve.html", services.building_overview(building))


def support(request):
    """경사로 설치 지원사업 안내 (기획 v2 6장). 신청은 대신하지 않고 안내·연결만"""
    region = Region.objects.filter(is_active=True).order_by("id").first()
    programs = SupportProgram.objects.filter(region=region, is_active=True) if region else []
    return render(request, "owners/support.html", {"programs": programs, "region": region})
