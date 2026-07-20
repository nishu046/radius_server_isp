"""Shared form plumbing.

TailwindFormMixin applies widget classes in Python so templates stay a
plain loop over ui/field.html. This replaces crispy-forms — the styling
lives in one place rather than being sprinkled through templates.
"""

from django import forms

BASE_INPUT = (
    'w-full rounded-card border border-line bg-surface px-3 py-2 text-sm '
    'text-ink placeholder:text-muted '
    'focus:border-brass focus:outline-none focus:ring-1 focus:ring-brass'
)

CHECKBOX = 'size-4 rounded-sm border-line-2 text-brass focus:ring-brass'

SELECT = BASE_INPUT + ' pr-8'

# Network values are monospace wherever they appear, including inputs.
MONO_FIELDS = {
    'ip', 'host', 'static_ip', 'mac_address', 'pppoe_username',
    'pppoe_password', 'serial', 'mac', 'account_no', 'reference',
}


class TailwindFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for name, field in self.fields.items():
            widget = field.widget
            existing = widget.attrs.get('class', '')

            if isinstance(widget, forms.CheckboxInput):
                css = CHECKBOX
            elif isinstance(widget, forms.CheckboxSelectMultiple):
                css = 'flex flex-col gap-1.5 text-sm text-ink'
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                css = SELECT
            elif isinstance(widget, forms.Textarea):
                css = BASE_INPUT
                widget.attrs.setdefault('rows', 4)
            else:
                css = BASE_INPUT

            if name in MONO_FIELDS:
                css += ' font-mono'

            # error state is visible at the field, not only in a summary
            if self.is_bound and self.errors.get(name):
                css += ' border-state-suspended'

            widget.attrs['class'] = f'{existing} {css}'.strip()

            if isinstance(widget, forms.DateInput):
                widget.input_type = 'date'
            elif isinstance(widget, forms.DateTimeInput):
                widget.input_type = 'datetime-local'


class TailwindForm(TailwindFormMixin, forms.Form):
    pass


class TailwindModelForm(TailwindFormMixin, forms.ModelForm):
    pass
