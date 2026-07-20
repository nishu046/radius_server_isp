"""Legacy routes. apps.packages is superseded by apps.billing (P1)."""

from django.urls import path
from django.views.generic import RedirectView

app_name = 'packages'

urlpatterns = [
    path('', RedirectView.as_view(pattern_name='billing:packages', permanent=False),
         name='packages'),
    path('create/', RedirectView.as_view(pattern_name='billing:package-create', permanent=False),
         name='create'),
]
