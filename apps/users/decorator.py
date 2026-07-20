# imports
from functools import wraps

from django.shortcuts import redirect


def anonymous_only(view_func):
    """Send already-authenticated users away from login/signup pages.

    Renamed from auth_user, which read as though it authenticated something.
    """

    @wraps(view_func)
    def wrapper_func(request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('dashboard:dashboard')
        return view_func(request, *args, **kwargs)

    return wrapper_func
