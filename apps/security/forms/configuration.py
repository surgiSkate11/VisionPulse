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
            # Métricas de Ojos
            'ear_threshold',
            'fatigue_threshold',
            'microsleep_duration_seconds',
            'blink_window_frames',
            
            # Tasa de Parpadeo
            'low_blink_rate_threshold',
            'high_blink_rate_threshold',
            
            # Boca y Bostezos
            'yawn_mar_threshold',
            
            # Pose de Cabeza
            'distraction_angle_threshold',
            'postural_rigidity_duration_seconds',
            
            # Ambiente
            'low_light_threshold',
            
            # Sistema de Monitoreo
            'monitoring_frequency',
            'break_reminder_interval',
            'face_detection_sensitivity',
            'sampling_interval_seconds',
            'camera_enabled',
            
            # Overlay Facial (Rendimiento)
            'face_overlay_enabled',
            'face_overlay_glow_intensity',
            'face_overlay_blur_sigma',
            
            # Interfaz y Notificaciones
            'dark_mode',
            'notification_mode',
            'alert_volume',
            'notify_inactive_tab',
            'email_notifications',
            
            # Privacidad y Datos
            'data_collection_consent',
            'anonymous_analytics',
            
            # Localización
            'locale',
            'timezone',
        ]
        widgets = {
            # Métricas de Ojos
            'ear_threshold': forms.NumberInput(attrs={'step': '0.01', 'min': 0.05, 'max': 0.40}),
            'fatigue_threshold': forms.NumberInput(attrs={'step': '0.01', 'min': 0.1, 'max': 1.0}),
            'microsleep_duration_seconds': forms.NumberInput(attrs={'step': '0.1', 'min': 0.8, 'max': 5.0}),
            'blink_window_frames': forms.NumberInput(attrs={'min': 1, 'max': 10}),
            
            # Tasa de Parpadeo
            'low_blink_rate_threshold': forms.NumberInput(attrs={'min': 3, 'max': 20}),
            'high_blink_rate_threshold': forms.NumberInput(attrs={'min': 25, 'max': 60}),
            
            # Boca y Bostezos
            'yawn_mar_threshold': forms.NumberInput(attrs={'step': '0.01', 'min': 0.4, 'max': 1.0}),
            
            # Pose de Cabeza
            'distraction_angle_threshold': forms.NumberInput(attrs={'min': 10, 'max': 45}),
            'postural_rigidity_duration_seconds': forms.NumberInput(attrs={'min': 60, 'max': 600}),
            
            # Ambiente
            'low_light_threshold': forms.NumberInput(attrs={'min': 30, 'max': 120}),
            
            # Sistema de Monitoreo
            'monitoring_frequency': forms.NumberInput(attrs={'min': 10, 'max': 300}),
            'break_reminder_interval': forms.NumberInput(attrs={'min': 5, 'max': 120}),
            'face_detection_sensitivity': forms.NumberInput(attrs={'step': '0.01', 'min': 0.1, 'max': 1.0}),
            'sampling_interval_seconds': forms.NumberInput(attrs={'min': 1, 'max': 60}),
            
            # Overlay Facial (Rendimiento)
            'face_overlay_glow_intensity': forms.NumberInput(attrs={'step': '0.01', 'min': 0.0, 'max': 1.0}),
            'face_overlay_blur_sigma': forms.NumberInput(attrs={'min': 1, 'max': 20}),
            
            # Interfaz y Notificaciones
            'alert_volume': forms.NumberInput(attrs={'step': '0.01', 'min': 0.0, 'max': 1.0}),
            'notification_mode': forms.Select(attrs={'class': 'form-control'}),
            
            # Localización
            'locale': forms.Select(attrs={'class': 'form-control'}),
            'timezone': forms.Select(attrs={'class': 'form-control'}),
        }
