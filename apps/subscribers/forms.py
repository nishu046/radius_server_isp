from django import forms

from apps.billing.models import Package
from apps.core.forms import TailwindModelForm
from apps.network.models import Router

from .models import Subscriber
from .services import generate_account_no, generate_pppoe_password


class SubscriberForm(TailwindModelForm):
    """Create/edit a subscriber.

    The connection-type toggle is driven by Alpine in the template; this
    form does the matching server-side validation, because a client-side
    toggle is a convenience, not a guarantee.
    """

    pppoe_password = forms.CharField(
        required=False,
        widget=forms.TextInput,
        help_text='Left blank on create, a password is generated. Readable '
                  'so support can give it to the customer.',
    )

    class Meta:
        model = Subscriber
        fields = [
            'account_no', 'name', 'phone', 'email', 'nid', 'address',
            'connection_type', 'pppoe_username', 'static_ip', 'mac_address',
            'router', 'package', 'pop', 'onu',
            'grace_days', 'auto_renew',
        ]
        labels = {
            'account_no': 'Account number',
            'nid': 'NID',
            'pppoe_username': 'PPPoE username',
            'static_ip': 'Static IP',
            'mac_address': 'MAC address',
            'pop': 'POP',
            'onu': 'ONU device',
            'grace_days': 'Grace period (days)',
        }
        help_texts = {
            'grace_days': 'Days online after expiry before suspension.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # only offer routers and packages that can actually be used
        self.fields['router'].queryset = Router.objects.filter(enabled=True)
        self.fields['package'].queryset = Package.objects.filter(is_active=True)

        if self.instance.pk:
            # keep a retired package selectable on an existing subscriber,
            # otherwise editing anything else silently reassigns their plan
            self.fields['package'].queryset = (
                Package.objects.filter(is_active=True)
                | Package.objects.filter(pk=self.instance.package_id)
            ).distinct()
            self.fields['pppoe_password'].initial = self.instance.get_pppoe_password()
        else:
            self.fields['account_no'].initial = generate_account_no()

    def clean(self):
        cleaned = super().clean()
        connection = cleaned.get('connection_type')

        if connection == Subscriber.Connection.PPPOE:
            if not cleaned.get('pppoe_username'):
                self.add_error('pppoe_username', 'Required for a PPPoE connection.')
            # a static IP left over from switching type would be provisioned
            cleaned['static_ip'] = None
            cleaned['mac_address'] = ''

        elif connection == Subscriber.Connection.STATIC_IP:
            if not cleaned.get('static_ip'):
                self.add_error('static_ip', 'Required for a static IP connection.')
            cleaned['pppoe_username'] = None

        return cleaned

    def save(self, commit=True):
        subscriber = super().save(commit=False)

        if subscriber.connection_type == Subscriber.Connection.PPPOE:
            password = self.cleaned_data.get('pppoe_password')
            subscriber.set_pppoe_password(password or generate_pppoe_password())
        else:
            subscriber.pppoe_password_enc = b''

        if commit:
            subscriber.save()
        return subscriber
