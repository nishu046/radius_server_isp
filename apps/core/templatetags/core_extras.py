from django import template

register = template.Library()


@register.filter
def has_perm(user, perm):
    """Permission check with a dotted string built at render time.

    The {% if perms.app.codename %} form needs a literal, so it cannot be
    used where the permission arrives as an {% include %} argument.
    """
    if not user or not user.is_authenticated:
        return False
    return user.has_perm(perm)


@register.filter
def field_type(field):
    return field.field.widget.__class__.__name__


@register.filter
def kbps(value):
    """Render a kbps integer the way an operator says it out loud."""
    try:
        value = int(value)
    except (TypeError, ValueError):
        return value
    if value >= 1000 and value % 1000 == 0:
        return f'{value // 1000}M'
    if value >= 1000:
        return f'{value / 1000:.1f}M'
    return f'{value}k'
