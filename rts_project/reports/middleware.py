"""Site-wide login enforcement, controlled by ``settings.REQUIRE_LOGIN``.

Set ``REQUIRE_LOGIN = True`` in ``config/settings.py`` to make every page
require a signed-in user (visitors get bounced to the login screen).
Set it to ``False`` to leave the whole site open — no login screen at all.
"""

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.urls import NoReverseMatch, reverse


class LoginRequiredMiddleware:
    """Redirect anonymous visitors to the login page when REQUIRE_LOGIN is on.

    A few paths are always left open so login itself can work:
    the login and logout views, the Django admin (it enforces its own
    login), and static files.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self._exempt = None

    def _exempt_prefixes(self):
        if self._exempt is None:
            paths = ["/admin/"]
            for name in ("login", "logout"):
                try:
                    paths.append(reverse(name))
                except NoReverseMatch:
                    pass
            static_url = getattr(settings, "STATIC_URL", "") or ""
            if static_url and not static_url.startswith(("http://", "https://", "//")):
                if not static_url.startswith("/"):
                    static_url = "/" + static_url
                paths.append(static_url)
            self._exempt = tuple(paths)
        return self._exempt

    def __call__(self, request):
        if getattr(settings, "REQUIRE_LOGIN", False):
            user = getattr(request, "user", None)
            if user is None or not user.is_authenticated:
                if not request.path_info.startswith(self._exempt_prefixes()):
                    return redirect_to_login(request.get_full_path())
        return self.get_response(request)
