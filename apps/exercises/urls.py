from django.urls import path
from . import views

app_name = 'exercises'

urlpatterns = [
    path('', views.exercise_list, name='exercise_list'),
    path('<int:pk>/', views.exercise_detail, name='exercise_detail'),
    path('<int:pk>/start/', views.start_exercise, name='start_exercise'),
    path('history/', views.exercise_history, name='exercise_history'),
    path('recommended/', views.recommended_exercises, name='recommended_exercises'),
]