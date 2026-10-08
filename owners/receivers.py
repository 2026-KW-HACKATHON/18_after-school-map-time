"""판정이 좋아지면 '가고 싶어요'를 누른 주민에게 알림 (기획 v2 6.2)"""

from django.dispatch import receiver

from accounts import notify
from judgments.constants import display
from judgments.signals import place_improved

from .models import VisitWish


@receiver(place_improved, dispatch_uid="owners_notify_wishers")
def notify_wishers(sender, judgment, **kwargs):
    label = display(judgment.result)["label"]
    wishes = VisitWish.objects.filter(place=judgment.place, profile=judgment.profile).select_related("user")
    for wish in wishes:
        notify.wish_place_improved(wish.user, judgment.place, judgment.profile, label)
