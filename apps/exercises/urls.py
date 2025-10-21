# apps/exercises/urls.py
from django.urls import path
from . import views

app_name = 'exercises'

urlpatterns = [
    # URL para mostrar el catálogo de ejercicios
    path('', views.ExerciseCatalogView.as_view(), name='catalog'),
    
    # URL de "API" para que JavaScript obtenga los datos de un ejercicio
    path('api/exercise/<int:pk>/', views.exercise_data, name='exercise_data'),
]