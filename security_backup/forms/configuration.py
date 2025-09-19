
from django import forms
from apps.security.models import User

# Formulario de perfil de usuario (datos personales)
class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = [
            'first_name', 'last_name', 'bio', 'birth_date', 'image',
            'phone', 'city', 'country', 'institution', 'major',
            'learning_style', 'preferred_study_time'
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
            'language', 'compact_view', 'show_motivational_quotes',
            'ai_assistance_level', 'auto_generate_summaries',
            'study_reminders', 'task_deadlines', 'achievement_notifications',
            'notifications_enabled', 'email_notifications', 'timezone_field'
        ]
        widgets = {
            'language': forms.Select(choices=[('es', 'Español'), ('en', 'Inglés')]),
            'ai_assistance_level': forms.Select(),
            'timezone_field': forms.TextInput(),
        }
from django.db import models
from django.utils import timezone
from django.core.validators import RegexValidator, MinValueValidator, MaxValueValidator
from apps.security.models import User
import uuid
