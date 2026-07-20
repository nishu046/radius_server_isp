from django.urls import path

from . import views

app_name = 'billing'

urlpatterns = [
    path('packages/', views.PackageListView.as_view(), name='packages'),
    path('packages/create/', views.PackageCreateView.as_view(), name='package-create'),
    path('packages/<int:pk>/edit/', views.PackageUpdateView.as_view(), name='package-update'),
    path('packages/<int:pk>/delete/', views.PackageDeleteView.as_view(), name='package-delete'),
]
