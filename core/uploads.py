"""
폼에 오류가 있어 다시 보여 줄 때 올린 사진을 잃지 않게 하기.

브라우저는 보안상 파일 칸을 다시 채워 주지 않는다 → 칸 하나만 잘못 적어도 사진을 다시 골라야 했다.
오류가 나면 올린 사진을 서버에 임시로 보관하고(EXIF 삭제·얼굴 가림 후), 폼에 서명된 표(token)를 숨겨 둔다.
다시 제출할 때 새 사진이 없으면 보관한 사진을 쓴다.

- 표는 Django 서명이라 다른 파일 경로로 바꿔치기할 수 없고, 하루가 지나면 무효
- 보관 파일 이름은 추측할 수 없는 무작위 이름, 하루 지난 보관 파일은 새로 보관할 때 함께 지운다
"""

import os
import time
import uuid

from django import forms
from django.core import signing
from django.core.files.base import File
from django.core.files.storage import default_storage

from .images import normalize_photo

TEMP_DIR = "upload_tmp"
# 사진 저작권 안내: 올린 사진은 공개되므로 남이 찍은 사진(인터넷·지도 로드뷰 캡처 등)을 올리면 저작권 침해가 될 수 있다.
# 사진 칸이 있는 모든 폼(주민 제보·사진 수정 요청·사장님 선언·정정·사진 교체)에 같은 문장을 붙인다 (setup_kept_photo)
PHOTO_RIGHTS_NOTICE = ("직접 찍은 사진만 올려 주세요. 인터넷·지도 로드뷰 캡처처럼 다른 사람의 사진은 저작권 때문에 올릴 수 없어요. "
                       "올린 사진은 확인을 거쳐 턱없네에 공개돼요.")
SALT = "teokeopne.kept-upload"
MAX_AGE = 60 * 60 * 24  # 하루


def _cleanup_old(now=None):
    now = now or time.time()
    try:
        _, files = default_storage.listdir(TEMP_DIR)
    except FileNotFoundError:
        return
    for name in files:
        path = f"{TEMP_DIR}/{name}"
        try:
            if now - default_storage.get_modified_time(path).timestamp() > MAX_AGE:
                default_storage.delete(path)
        except (FileNotFoundError, OSError):
            continue


def keep(upload):
    """올린 파일을 임시 보관하고 서명된 표를 돌려준다"""
    _cleanup_old()
    cleaned = normalize_photo(upload, name=getattr(upload, "name", "photo"))
    name = default_storage.save(f"{TEMP_DIR}/{uuid.uuid4().hex}.jpg", cleaned)
    return signing.dumps(name, salt=SALT)


def _name(token):
    try:
        name = signing.loads(token, salt=SALT, max_age=MAX_AGE)
    except signing.BadSignature:
        return None
    if not isinstance(name, str) or not name.startswith(f"{TEMP_DIR}/") or not default_storage.exists(name):
        return None
    return name


def restore(token):
    """표 → 보관한 파일 (없거나 만료면 None)"""
    name = _name(token)
    if name is None:
        return None
    return File(default_storage.open(name, "rb"), name=os.path.basename(name))


def url(token):
    name = _name(token)
    return default_storage.url(name) if name else ""


def discard(token):
    name = _name(token)
    if name:
        default_storage.delete(name)


class KeepPhotoMixin:
    """
    사진 칸(photo)이 있는 폼에 섞어 쓴다. 폼 __init__ 끝에서 self.setup_kept_photo() 를 부르고,
    오류로 다시 보여 주기 직전에 form.keep_photo_for_retry() 를 부른다.
    """

    def setup_kept_photo(self):
        photo = self.fields["photo"]
        if PHOTO_RIGHTS_NOTICE not in (photo.help_text or ""):  # 저작권 안내 (모든 사진 칸 공통)
            photo.help_text = f"{photo.help_text} {PHOTO_RIGHTS_NOTICE}".strip()
        self.fields["photo_token"] = forms.CharField(required=False, widget=forms.HiddenInput)
        self.kept_photo = None
        token = self.data.get("photo_token") if self.is_bound else ""
        if token and not self.files.get("photo"):
            self.kept_photo = restore(token)
            if self.kept_photo is not None:
                self.fields["photo"].required = False  # 보관한 사진이 있으니 다시 고르지 않아도 됨

    def clean_photo(self):
        return self.cleaned_data.get("photo") or self.kept_photo

    def keep_photo_for_retry(self):
        """오류가 있을 때: 이번에 새로 올린 사진을 보관하고 숨은 칸에 표를 넣는다"""
        if not self.is_bound or not self.errors:
            return
        photo = getattr(self, "cleaned_data", {}).get("photo")
        if photo is not None and photo is not self.kept_photo:
            token = keep(photo)
            self.data = self.data.copy()
            self.data["photo_token"] = token
            # The retry page already has a valid photo; do not require a new file in the browser.
            self.fields["photo"].required = False

    @property
    def kept_photo_url(self):
        token = self.data.get("photo_token") if self.is_bound else ""
        return url(token) if token else ""
