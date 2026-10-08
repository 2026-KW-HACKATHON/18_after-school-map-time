from pathlib import Path

from django.contrib.staticfiles.storage import ManifestStaticFilesStorage


class CacheBustingStaticStorage(ManifestStaticFilesStorage):
    """
    배포(DEBUG=False)용 정적 파일 저장소.
    collectstatic 때 파일 이름에 내용 해시를 붙인다 (common.css → common.4e5741f6b0a2.css).
    CSS·JS를 고치면 주소가 바뀌므로, nginx가 7일 캐시를 걸어도 브라우저가 옛 파일을 쓰지 않는다.

    새 worker는 collectstatic 완료 후 시작한다. 수동 정적 파일 재수집 시에도
    worker별로 기억한 manifest를 갱신해 같은 페이지에서 서로 다른 CSS를 쓰지 않는다.
    아직 모아지지 않은 새 파일은 500 대신 해시 없는 원래 이름을 돌려준다.
    """

    manifest_strict = False

    def manifest_signature(self):
        try:
            stat = Path(self.manifest_storage.path(self.manifest_name)).stat()
            return stat.st_mtime_ns, stat.st_size
        except FileNotFoundError:
            return None

    def load_manifest(self):
        self._manifest_signature = self.manifest_signature()
        return super().load_manifest()

    def stored_name(self, name):
        if self.manifest_signature() != self._manifest_signature:
            self.hashed_files, self.manifest_hash = self.load_manifest()
        try:
            return super().stored_name(name)
        except ValueError:
            return name
