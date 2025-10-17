from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Exercise, ExerciseSession
from .forms.exercises import ExerciseForm, ExerciseSessionForm

@login_required
def exercise_list(request):
    exercises = Exercise.objects.all()
    context = {
        'exercises': exercises,
        'section': 'exercises'
    }
    return render(request, 'exercises/exercise_list.html', context)

@login_required
def exercise_detail(request, pk):
    exercise = get_object_or_404(Exercise, pk=pk)
    if request.method == 'POST':
        form = ExerciseSessionForm(request.POST)
        if form.is_valid():
            session = form.save(commit=False)
            session.user = request.user
            session.exercise = exercise
            session.save()
            messages.success(request, '¡Ejercicio completado exitosamente!')
            return redirect('exercises:exercise_list')
    else:
        form = ExerciseSessionForm(initial={'exercise': exercise})
    
    context = {
        'exercise': exercise,
        'form': form,
        'section': 'exercises'
    }
    return render(request, 'exercises/exercise_detail.html', context)

@login_required
def start_exercise(request, pk):
    exercise = get_object_or_404(Exercise, pk=pk)
    context = {
        'exercise': exercise,
        'section': 'exercises'
    }
    return render(request, 'exercises/start_exercise.html', context)

@login_required
def exercise_history(request):
    sessions = ExerciseSession.objects.filter(user=request.user).order_by('-created_at')
    context = {
        'sessions': sessions,
        'section': 'exercises'
    }
    return render(request, 'exercises/exercise_history.html', context)

@login_required
def recommended_exercises(request):
    # Lógica para recomendar ejercicios basados en el monitoreo y fatiga visual
    exercises = Exercise.objects.all()[:5]  # Placeholder: mostrar 5 ejercicios
    context = {
        'exercises': exercises,
        'section': 'exercises'
    }
    return render(request, 'exercises/recommended_exercises.html', context)
