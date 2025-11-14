from django.urls import path
from .views import ProfileView, UserSettingsView, DashboardView

urlpatterns = [
    path('profile/', ProfileView.as_view(), name='profile'),
    path('user-settings/', UserSettingsView.as_view(), name='user_settings'),
    path('dashboard/', DashboardView.as_view(), name='dashboard'),
]
