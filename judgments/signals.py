from django.dispatch import Signal

# 판정이 한 단계 이상 좋아졌을 때 보냄 (engine.recompute_place). 인자: judgment
# 사장님 앱(owners)이 받아서 '가고 싶어요'를 누른 주민에게 알림 → judgments는 owners를 몰라도 됨
place_improved = Signal()
