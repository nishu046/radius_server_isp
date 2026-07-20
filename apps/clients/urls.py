"""Legacy routes.

apps.clients is superseded by apps.subscribers (P1). The model and its
migrations stay so the historical data migration remains reversible, but
the screens are gone — these redirect anyone with an old bookmark.
"""

from django.urls import path
from django.views.generic import RedirectView

app_name = 'client'

urlpatterns = [
    path('', RedirectView.as_view(pattern_name='subscribers:list', permanent=False),
         name='clients'),
    path('create/', RedirectView.as_view(pattern_name='subscribers:create', permanent=False),
         name='create'),
]
