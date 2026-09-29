from django.contrib.staticfiles.storage import ManifestStaticFilesStorage


class CacheBustingStaticStorage(ManifestStaticFilesStorage):
    """
    배포(DEBUG=False)용 정적 파일 저장소.
    collectstatic 때 파일 이름에 내용 해시를 붙인다 (common.css → common.4e5741f6b0a2.css).
    CSS·JS를 고치면 주소가 바뀌므로, nginx가 7일 캐시를 걸어도 브라우저가 옛 파일을 쓰지 않는다.

    배포 순서상 새 코드가 먼저 뜨고 collectstatic이 몇 초 늦게 끝난다.
    그 사이 아직 모아지지 않은 새 파일을 요청해도 500 에러 대신 해시 없는 원래 이름을 돌려준다.
    """

    manifest_strict = False

    def stored_name(self, name):
        try:
            return super().stored_name(name)
        except ValueError:
            return name
