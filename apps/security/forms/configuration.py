
from django import forms
from apps.security.models import User

# Formulario de perfil de usuario (datos personales)
class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = [
            'first_name', 'last_name', 'bio', 'birth_date', 'image',
            'phone', 'city', 'country', 'company', 'job_title',
            'user_type', 'work_environment', 'screen_size', 'preferred_work_time'
        ]
        widgets = {
            'birth_date': forms.DateInput(attrs={'type': 'date'}),
            'bio': forms.Textarea(attrs={'rows': 3}),
        }

# Formulario de configuración/preferencias
class SettingsForm(forms.ModelForm):
    class Meta:
        model = User
        fields = [
            'language', 'monitoring_frequency', 'break_reminder_interval', 
            'auto_pause_on_fatigue', 'exercise_difficulty', 'auto_suggest_exercises',
            'visual_fatigue_alerts', 'break_reminders', 'daily_reports',
            'notifications_enabled', 'email_notifications', 'timezone_field'
        ]
        widgets = {
            'language': forms.Select(choices=[('es', 'Español'), ('en', 'Inglés')]),
            'exercise_difficulty': forms.Select(),
            'timezone_field': forms.TextInput(),
            'monitoring_frequency': forms.NumberInput(attrs={'min': 10, 'max': 300}),
            'break_reminder_interval': forms.NumberInput(attrs={'min': 5, 'max': 120}),
        }
from django.db import models
from django.utils import timezone
from django.core.validators import RegexValidator, MinValueValidator, MaxValueValidator
from apps.security.models import User
import uuid
