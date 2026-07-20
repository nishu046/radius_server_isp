from django.urls import path

from . import views

app_name = 'subscribers'

urlpatterns = [
    path('', views.SubscriberListView.as_view(), name='list'),
    path('create/', views.SubscriberCreateView.as_view(), name='create'),
    path('<int:pk>/', views.SubscriberDetailView.as_view(), name='detail'),
    path('<int:pk>/edit/', views.SubscriberUpdateView.as_view(), name='update'),
    path('<int:pk>/delete/', views.SubscriberDeleteView.as_view(), name='delete'),
    path('<int:pk>/state/<str:to_state>/', views.change_state, name='change-state'),
]
