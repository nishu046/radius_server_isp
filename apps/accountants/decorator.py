# imports
from functools import wraps

from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect

from apps.users.models import ROLE_OWNER


def owner_roles(view_func):
    """Restrict a view to owners.

    Previously read request.user.owner, a boolean that no longer exists —
    roles are groups now. Unauthorised access raises 403 rather than silently
    redirecting to the client list, which made the restriction invisible.
    """

    @wraps(view_func)
    def wrapper_func(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')

        if request.user.is_superuser or request.user.in_role(ROLE_OWNER):
            return view_func(request, *args, **kwargs)

        raise PermissionDenied

    return wrapper_func
