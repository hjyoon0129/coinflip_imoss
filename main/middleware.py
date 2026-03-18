from django.shortcuts import redirect

from user.models import UserProfile


class RequireNicknameMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)

        if user and user.is_authenticated:
            path = request.path

            allowed_prefixes = (
                "/user/edit-nickname/",
                "/accounts/",
                "/admin/",
                "/static/",
                "/media/",
            )

            if not path.startswith(allowed_prefixes):
                profile, _ = UserProfile.objects.get_or_create(user=user)
                nickname = (profile.nickname or "").strip()

                if not nickname:
                    return redirect(f"/user/edit-nickname/?next={path}")

        response = self.get_response(request)
        return response