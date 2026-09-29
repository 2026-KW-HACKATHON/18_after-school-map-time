from allauth.socialaccount.adapter import DefaultSocialAccountAdapter


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    """카카오 로그인으로 처음 들어온 사용자를 자동 가입시킬 때의 동작"""

    def is_open_for_signup(self, request, sociallogin):
        # 아이디·비밀번호 가입은 막혀 있지만(SOCIALACCOUNT_ONLY) 카카오 가입은 항상 허용
        return True

    def populate_user(self, request, sociallogin, data):
        user = super().populate_user(request, sociallogin, data)
        # 카카오 프로필 닉네임을 화면 표시용으로 저장 (동의 항목: 닉네임)
        profile = sociallogin.account.extra_data.get("kakao_account", {}).get("profile", {})
        user.nickname = (profile.get("nickname") or "")[:30]
        return user
