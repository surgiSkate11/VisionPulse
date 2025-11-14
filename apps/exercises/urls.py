# apps/exercises/urls.py
from django.urls import path
from . import views

app_name = 'exercises'

urlpatterns = [
    # URL para mostrar el catálogo de ejercicios
    path('', views.ExerciseCatalogView.as_view(), name='catalog'),
    
    # URL de "API" para que JavaScript obtenga los datos de un ejercicio
    path('api/exercise/<int:pk>/', views.exercise_data, name='exercise_data'),
    
    # URLs para gestionar sesiones de ejercicios
    path('api/session/start/<int:exercise_id>/', views.start_exercise_session, name='start_session'),
    path('api/session/complete/<int:session_id>/', views.complete_exercise_session, name='complete_session'),
    path('api/session/cancel/<int:session_id>/', views.cancel_exercise_session, name='cancel_session'),
]