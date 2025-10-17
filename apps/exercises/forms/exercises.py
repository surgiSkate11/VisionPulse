from django import forms
from apps.exercises.models import Exercise, ExerciseSession

class ExerciseForm(forms.ModelForm):
    class Meta:
        model = Exercise
        fields = ['title', 'description', 'duration_minutes', 'type', 'video_link', 'instruction_steps']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Nombre del ejercicio'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-textarea',
                'rows': 3,
                'placeholder': 'Descripción breve del ejercicio'
            }),
            'duration_minutes': forms.NumberInput(attrs={
                'class': 'form-input',
                'min': 1,
                'placeholder': 'Duración en minutos'
            }),
            'type': forms.Select(attrs={'class': 'form-select'}),
            'video_link': forms.URLInput(attrs={
                'class': 'form-input',
                'placeholder': 'URL del video (opcional)'
            }),
            'instruction_steps': forms.Textarea(attrs={
                'class': 'form-textarea',
                'rows': 5,
                'placeholder': 'Pasos detallados del ejercicio'
            }),
        }

class ExerciseSessionForm(forms.ModelForm):
    class Meta:
        model = ExerciseSession
        fields = ['completed', 'rating', 'feedback']
        widgets = {
            'completed': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
            'rating': forms.NumberInput(attrs={
                'class': 'form-input',
                'min': 1,
                'max': 5,
                'placeholder': 'Calificación (1-5)'
            }),
            'feedback': forms.Textarea(attrs={
                'class': 'form-textarea',
                'rows': 3,
                'placeholder': 'Tu experiencia con este ejercicio'
            }),
        }
