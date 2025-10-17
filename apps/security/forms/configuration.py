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
            'ear_threshold',
            'blink_window_frames',
            'blink_rate_threshold',
            'monitoring_frequency',
            'break_reminder_interval',
            'dark_mode',
            'notification_mode',
            'alert_volume',
            'data_collection_consent',
            'anonymous_analytics',
            'camera_enabled',
            'face_detection_sensitivity',
            'fatigue_threshold',
            'sampling_interval_seconds',
            'notify_inactive_tab',
            'locale',
            'timezone',
        ]
        widgets = {
            'ear_threshold': forms.NumberInput(attrs={'step': '0.01'}),
            'blink_window_frames': forms.NumberInput(attrs={'min': 1, 'max': 10}),
            'blink_rate_threshold': forms.NumberInput(attrs={'min': 5, 'max': 30}),
            'monitoring_frequency': forms.NumberInput(attrs={'min': 10, 'max': 300}),
            'break_reminder_interval': forms.NumberInput(attrs={'min': 5, 'max': 120}),
            'alert_volume': forms.NumberInput(attrs={'step': '0.01', 'min': 0.0, 'max': 1.0}),
            'face_detection_sensitivity': forms.NumberInput(attrs={'step': '0.01', 'min': 0.1, 'max': 1.0}),
            'fatigue_threshold': forms.NumberInput(attrs={'step': '0.01', 'min': 0.1, 'max': 1.0}),
            'sampling_interval_seconds': forms.NumberInput(attrs={'min': 1, 'max': 60}),
            'locale': forms.Select(attrs={'class': 'form-control'}),
            'timezone': forms.Select(attrs={'class': 'form-control'}),
            'notification_mode': forms.Select(attrs={'class': 'form-control'}),
        }
