"""요청에서 받은 DB 식별자 검증. 인증 코드 등 다른 숫자 문자열에는 사용하지 않는다."""

MAX_PK = 2**63 - 1  # SQLite / PostgreSQL의 BigAutoField 범위


def parse_pk(raw):
    """양의 ASCII 정수만 반환한다. 잘못된 값은 DB에 전달하지 않는다."""
    if not isinstance(raw, str) or not raw.isascii() or not raw.isdecimal():
        return None
    digits = raw.lstrip("0")
    maximum = str(MAX_PK)
    # 변환 전에 길이도 확인: 거대한 입력의 int() 제한·DB overflow를 피한다.
    if not digits or len(digits) > len(maximum) or (len(digits) == len(maximum) and digits > maximum):
        return None
    return int(digits)
