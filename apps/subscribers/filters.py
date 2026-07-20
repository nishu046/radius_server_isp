import django_filters
from django import forms
from django.db.models import Q

from apps.billing.models import Package
from apps.network.models import Router

from .models import Subscriber


class SubscriberFilter(django_filters.FilterSet):
    q = django_filters.CharFilter(
        method='search',
        label='Search',
        widget=forms.TextInput(attrs={
            'placeholder': 'Name, account no, phone, username or IP',
        }),
    )
    service_state = django_filters.ChoiceFilter(
        choices=Subscriber.State.choices, label='State', empty_label='Any state')
    package = django_filters.ModelChoiceFilter(
        queryset=Package.objects.all(), empty_label='Any package')
    router = django_filters.ModelChoiceFilter(
        queryset=Router.objects.all(), empty_label='Any router')
    sync_state = django_filters.ChoiceFilter(
        choices=Subscriber.Sync.choices, label='Sync', empty_label='Any sync state')

    class Meta:
        model = Subscriber
        fields = ['q', 'service_state', 'package', 'router', 'sync_state']

    def search(self, queryset, name, value):
        """One box across every identifier an operator might have to hand —
        a customer on the phone gives whichever they know."""
        return queryset.filter(
            Q(name__icontains=value)
            | Q(account_no__icontains=value)
            | Q(phone__icontains=value)
            | Q(pppoe_username__icontains=value)
            | Q(static_ip__icontains=value)
            | Q(email__icontains=value)
        )
