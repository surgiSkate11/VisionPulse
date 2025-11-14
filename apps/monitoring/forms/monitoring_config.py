from django import forms
from apps.monitoring.models import UserMonitoringConfig
from django.core.exceptions import ValidationError


class UserMonitoringConfigForm(forms.ModelForm):
    """
    Formulario para que el usuario edite su configuración de monitoreo.
    Incluye validaciones de rangos tanto en backend como en frontend.
    """
    
    class Meta:
        model = UserMonitoringConfig
        fields = [
            # Detección ocular y microsueño
            'ear_threshold',
            'microsleep_duration_seconds',
            # Tasa de parpadeo y luz
            'low_blink_rate_threshold',
            'high_blink_rate_threshold',
            'low_light_threshold',
            # Frecuencias / sampling / descansos
            'monitoring_frequency',
            'break_reminder_interval',
            'sampling_interval_seconds',
            # Cámara
            'camera_enabled',
            # Temporizadores de detección / histéresis / cooldown
            'detection_delay_seconds',
            'hysteresis_timeout_seconds',
            'alert_cooldown_seconds',
            # Repetición de alertas
            'alert_repeat_interval',
            'repeat_max_per_hour',
            # UI / Notificaciones
            'dark_mode',
            'alert_volume',
            'notify_inactive_tab',
            'email_notifications',
            # Privacidad / Preferencias
            'data_collection_consent',
            'anonymous_analytics',
            'locale',
            'timezone',
        ]
        
        widgets = {
            'ear_threshold': forms.NumberInput(attrs={
                'class': 'form-input w-full px-4 py-2.5 rounded-lg border border-border-color dark:border-dark-border-color bg-surface dark:bg-dark-surface text-text-primary dark:text-dark-text-primary focus:ring-2 focus:ring-warm-orange-400 focus:border-transparent transition',
                'step': '0.01',
                'min': '0.05',
                'max': '0.40',
            }),
            'microsleep_duration_seconds': forms.NumberInput(attrs={
                'class': 'form-input w-full px-4 py-2.5 rounded-lg border border-border-color dark:border-dark-border-color bg-surface dark:bg-dark-surface text-text-primary dark:text-dark-text-primary focus:ring-2 focus:ring-warm-orange-400 focus:border-transparent transition',
                'step': '0.5',
                'min': '5.0',
                'max': '15.0',
            }),
            'low_blink_rate_threshold': forms.NumberInput(attrs={
                'class': 'form-input w-full px-4 py-2.5 rounded-lg border border-border-color dark:border-dark-border-color bg-surface dark:bg-dark-surface text-text-primary dark:text-dark-text-primary focus:ring-2 focus:ring-warm-orange-400 focus:border-transparent transition',
                'min': '3',
                'max': '20',
            }),
            'high_blink_rate_threshold': forms.NumberInput(attrs={
                'class': 'form-input w-full px-4 py-2.5 rounded-lg border border-border-color dark:border-dark-border-color bg-surface dark:bg-dark-surface text-text-primary dark:text-dark-text-primary focus:ring-2 focus:ring-warm-orange-400 focus:border-transparent transition',
                'min': '25',
                'max': '60',
            }),
            'low_light_threshold': forms.NumberInput(attrs={
                'class': 'form-input w-full px-4 py-2.5 rounded-lg border border-border-color dark:border-dark-border-color bg-surface dark:bg-dark-surface text-text-primary dark:text-dark-text-primary focus:ring-2 focus:ring-warm-orange-400 focus:border-transparent transition',
                'min': '30',
                'max': '120',
            }),
            'monitoring_frequency': forms.NumberInput(attrs={
                'class': 'form-input w-full px-4 py-2.5 rounded-lg border border-border-color dark:border-dark-border-color bg-surface dark:bg-dark-surface text-text-primary dark:text-dark-text-primary focus:ring-2 focus:ring-warm-orange-400 focus:border-transparent transition',
                'min': '10',
                'max': '300',
            }),
            'break_reminder_interval': forms.NumberInput(attrs={
                'class': 'form-input w-full px-4 py-2.5 rounded-lg border border-border-color dark:border-dark-border-color bg-surface dark:bg-dark-surface text-text-primary dark:text-dark-text-primary focus:ring-2 focus:ring-warm-orange-400 focus:border-transparent transition',
                'min': '5',
                'max': '120',
            }),
            'sampling_interval_seconds': forms.NumberInput(attrs={
                'class': 'form-input w-full px-4 py-2.5 rounded-lg border border-border-color dark:border-dark-border-color bg-surface dark:bg-dark-surface text-text-primary dark:text-dark-text-primary focus:ring-2 focus:ring-warm-orange-400 focus:border-transparent transition',
                'min': '1',
                'max': '60',
            }),
            'alert_repeat_interval': forms.NumberInput(attrs={
                'class': 'form-input w-full px-4 py-2.5 rounded-lg border border-border-color dark:border-dark-border-color bg-surface dark:bg-dark-surface text-text-primary dark:text-dark-text-primary focus:ring-2 focus:ring-warm-orange-400 focus:border-transparent transition',
                'min': '1',
                'max': '50',
            }),
            'repeat_max_per_hour': forms.NumberInput(attrs={
                'class': 'form-input w-full px-4 py-2.5 rounded-lg border border-border-color dark:border-dark-border-color bg-surface dark:bg-dark-surface text-text-primary dark:text-dark-text-primary focus:ring-2 focus:ring-warm-orange-400 focus:border-transparent transition',
                'min': '1',
                'max': '60',
            }),
            'alert_volume': forms.NumberInput(attrs={
                'class': 'form-input w-full px-4 py-2.5 rounded-lg border border-border-color dark:border-dark-border-color bg-surface dark:bg-dark-surface text-text-primary dark:text-dark-text-primary focus:ring-2 focus:ring-warm-orange-400 focus:border-transparent transition',
                'step': '0.1',
                'min': '0.0',
                'max': '1.0',
                'type': 'range',
            }),
            'camera_enabled': forms.CheckboxInput(attrs={
                'class': 'form-checkbox h-5 w-5 text-warm-orange-500 rounded border-border-color dark:border-dark-border-color focus:ring-2 focus:ring-warm-orange-400',
            }),
            'detection_delay_seconds': forms.NumberInput(attrs={
                'class': 'form-input w-full px-4 py-2.5 rounded-lg border border-border-color dark:border-dark-border-color bg-surface dark:bg-dark-surface text-text-primary dark:text-dark-text-primary focus:ring-2 focus:ring-warm-orange-400 focus:border-transparent transition',
                'min': '1',
                'max': '3600',
            }),
            'hysteresis_timeout_seconds': forms.NumberInput(attrs={
                'class': 'form-input w-full px-4 py-2.5 rounded-lg border border-border-color dark:border-dark-border-color bg-surface dark:bg-dark-surface text-text-primary dark:text-dark-text-primary focus:ring-2 focus:ring-warm-orange-400 focus:border-transparent transition',
                'min': '5',
                'max': '3600',
            }),
            'alert_cooldown_seconds': forms.NumberInput(attrs={
                'class': 'form-input w-full px-4 py-2.5 rounded-lg border border-border-color dark:border-dark-border-color bg-surface dark:bg-dark-surface text-text-primary dark:text-dark-text-primary focus:ring-2 focus:ring-warm-orange-400 focus:border-transparent transition',
                'min': '5',
                'max': '3600',
            }),
            'notify_inactive_tab': forms.CheckboxInput(attrs={
                'class': 'form-checkbox h-5 w-5 text-warm-orange-500 rounded border-border-color dark:border-dark-border-color focus:ring-2 focus:ring-warm-orange-400',
            }),
            'email_notifications': forms.CheckboxInput(attrs={
                'class': 'form-checkbox h-5 w-5 text-warm-orange-500 rounded border-border-color dark:border-dark-border-color focus:ring-2 focus:ring-warm-orange-400',
            }),
            'dark_mode': forms.CheckboxInput(attrs={
                'class': 'form-checkbox h-5 w-5 text-warm-orange-500 rounded border-border-color dark:border-dark-border-color focus:ring-2 focus:ring-warm-orange-400',
            }),
            'data_collection_consent': forms.CheckboxInput(attrs={
                'class': 'form-checkbox h-5 w-5 text-warm-orange-500 rounded border-border-color dark:border-dark-border-color focus:ring-2 focus:ring-warm-orange-400',
            }),
            'anonymous_analytics': forms.CheckboxInput(attrs={
                'class': 'form-checkbox h-5 w-5 text-warm-orange-500 rounded border-border-color dark:border-dark-border-color focus:ring-2 focus:ring-warm-orange-400',
            }),
            'locale': forms.TextInput(attrs={
                'class': 'form-input w-full px-4 py-2.5 rounded-lg border border-border-color dark:border-dark-border-color bg-surface dark:bg-dark-surface text-text-primary dark:text-dark-text-primary focus:ring-2 focus:ring-warm-orange-400 focus:border-transparent transition',
                'maxlength': '10',
            }),
            'timezone': forms.TextInput(attrs={
                'class': 'form-input w-full px-4 py-2.5 rounded-lg border border-border-color dark:border-dark-border-color bg-surface dark:bg-dark-surface text-text-primary dark:text-dark-text-primary focus:ring-2 focus:ring-warm-orange-400 focus:border-transparent transition',
                'maxlength': '50',
            }),
        }
        
        labels = {
            'ear_threshold': 'Umbral de Apertura Ocular (EAR)',
            'microsleep_duration_seconds': 'Duración de Microsueño (segundos)',
            'low_blink_rate_threshold': 'Umbral de Parpadeo Bajo (por minuto)',
            'high_blink_rate_threshold': 'Umbral de Parpadeo Alto (por minuto)',
            'low_light_threshold': 'Umbral de Luz Baja',
            'monitoring_frequency': 'Frecuencia de Análisis (segundos)',
            'break_reminder_interval': 'Recordatorio de Descanso (minutos)',
            'sampling_interval_seconds': 'Intervalo de Muestreo (segundos)',
            'camera_enabled': 'Cámara Habilitada',
            'detection_delay_seconds': 'Retraso de Detección (segundos)',
            'hysteresis_timeout_seconds': 'Tiempo de Histéresis (segundos)',
            'alert_cooldown_seconds': 'Cooldown de Alertas (segundos)',
            'alert_repeat_interval': 'Intervalo de Repetición de Alertas (segundos)',
            'repeat_max_per_hour': 'Máximo de Repeticiones por Hora',
            'alert_volume': 'Volumen de Alertas',
            'notify_inactive_tab': 'Notificar en Pestaña Inactiva',
            'email_notifications': 'Notificaciones por Email',
            'dark_mode': 'Modo Oscuro',
            'data_collection_consent': 'Consentimiento de Recolección de Datos',
            'anonymous_analytics': 'Analíticas Anónimas',
            'locale': 'Idioma',
            'timezone': 'Zona Horaria',
        }
        
        help_texts = {
            'ear_threshold': 'Más bajo = más sensible (0.05 - 0.40)',
            'microsleep_duration_seconds': 'Tiempo para detectar microsueño (5.0 - 15.0 segundos)',
            'low_blink_rate_threshold': 'Parpadeos por minuto considerados bajos (3 - 20)',
            'high_blink_rate_threshold': 'Parpadeos por minuto considerados altos (25 - 60)',
            'low_light_threshold': 'Nivel de luminancia considerado bajo (30 - 120)',
            'monitoring_frequency': 'Cada cuántos segundos se analiza (10 - 300)',
            'break_reminder_interval': 'Cada cuántos minutos recordar descanso (5 - 120)',
            'sampling_interval_seconds': 'Intervalo entre muestras (1 - 60)',
            'detection_delay_seconds': 'Segundos continuos antes de disparar una alerta (1 - 3600)',
            'hysteresis_timeout_seconds': 'Segundos necesarios en estado normal para considerar resuelta (5 - 3600)',
            'alert_cooldown_seconds': 'Tiempo mínimo entre alertas del mismo tipo (5 - 3600)',
            'alert_repeat_interval': 'Tiempo entre repeticiones de alerta (1 - 50 segundos)',
            'repeat_max_per_hour': 'Número máximo de repeticiones por hora (1 - 60)',
            'alert_volume': 'Volumen de las alertas sonoras (0.0 - 1.0)',
        }
    
    def clean_ear_threshold(self):
        value = self.cleaned_data['ear_threshold']
        if not (0.05 <= value <= 0.40):
            raise ValidationError('El umbral EAR debe estar entre 0.05 y 0.40')
        return value
    
    # Validaciones adicionales de nuevos campos (coherentes con validators del modelo)
    def clean_detection_delay_seconds(self):
        v = self.cleaned_data['detection_delay_seconds']
        if not (1 <= v <= 3600):
            raise ValidationError('El retraso de detección debe estar entre 1 y 3600 segundos')
        return v

    def clean_hysteresis_timeout_seconds(self):
        v = self.cleaned_data['hysteresis_timeout_seconds']
        if not (5 <= v <= 3600):
            raise ValidationError('El tiempo de histéresis debe estar entre 5 y 3600 segundos')
        return v

    def clean_alert_cooldown_seconds(self):
        v = self.cleaned_data['alert_cooldown_seconds']
        if not (5 <= v <= 3600):
            raise ValidationError('El cooldown debe estar entre 5 y 3600 segundos')
        return v
    
    def clean_microsleep_duration_seconds(self):
        value = self.cleaned_data['microsleep_duration_seconds']
        if not (5.0 <= value <= 15.0):
            raise ValidationError('La duración de microsueño debe estar entre 5.0 y 15.0 segundos')
        return value
    
    def clean_low_blink_rate_threshold(self):
        value = self.cleaned_data['low_blink_rate_threshold']
        if not (3 <= value <= 20):
            raise ValidationError('El umbral de parpadeo bajo debe estar entre 3 y 20')
        return value
    
    def clean_high_blink_rate_threshold(self):
        value = self.cleaned_data['high_blink_rate_threshold']
        if not (25 <= value <= 60):
            raise ValidationError('El umbral de parpadeo alto debe estar entre 25 y 60')
        return value
    
    def clean(self):
        cleaned_data = super().clean()
        low_blink = cleaned_data.get('low_blink_rate_threshold')
        high_blink = cleaned_data.get('high_blink_rate_threshold')
        if low_blink and high_blink and low_blink >= high_blink:
            raise ValidationError('El umbral de parpadeo bajo debe ser menor que el umbral alto')
        
        return cleaned_data
