from django.dispatch import Signal

# 제보가 반영(VERIFIED)되거나 반려(REJECTED)됐을 때 보냄. 인자: report
# 판정 앱(judgments)이 이 신호를 받아 해당 장소를 다시 판정한다 → reports는 judgments를 몰라도 됨
report_reviewed = Signal()
