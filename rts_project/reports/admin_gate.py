"""Separate admin sign-in for the clinic & machine management pages.

The credentials live in ``config/settings.py`` as ``MANAGE_ADMIN_USERNAME``
and ``MANAGE_ADMIN_PASSWORD``. This is independent of the site-wide login
(``REQUIRE_LOGIN``) and of the Django admin at /admin/.
"""

from functools import wraps
from urllib.parse import urlencode

from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse

SESSION_KEY = "manage_admin_ok"


def is_manage_admin(request):
    return bool(request.session.get(SESSION_KEY))


def manage_admin_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if is_manage_admin(request):
            return view(request, *args, **kwargs)
        query = urlencode({"next": request.get_full_path()})
        return redirect(f"{reverse('reports:manage_login')}?{query}")

    return wrapper


def check_credentials(username, password):
    return (
        username == getattr(settings, "MANAGE_ADMIN_USERNAME", "")
        and password == getattr(settings, "MANAGE_ADMIN_PASSWORD", "")
    )
