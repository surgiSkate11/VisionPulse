from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
import re
from apps.security.models import User
from apps.monitoring.models import UserMonitoringConfig

# Formulario de perfil de usuario (datos personales)
class ProfileForm(forms.ModelForm):
    email = forms.EmailField(
        label='Email',
        required=True,
        help_text='Email único y válido para notificaciones y recuperación de cuenta',
        widget=forms.EmailInput(attrs={
            'type': 'email',
            'autocomplete': 'email',
            'required': 'required',
            'maxlength': '254',
            'placeholder': 'ejemplo@correo.com',
        })
    )

    class Meta:
        model = User
        fields = [
            'first_name', 'last_name', 'email', 'bio', 'birth_date', 'image',
            'phone', 'city', 'country', 'company', 'job_title',
            'user_type', 'work_environment', 'screen_size', 'preferred_work_time',
            'notification_sound', 'notification_sound_enabled'
        ]
        
        labels = {
            'first_name': 'Nombre',
            'last_name': 'Apellido',
            'email': 'Correo Electrónico',
            'bio': 'Biografía',
            'birth_date': 'Fecha de Nacimiento',
            'image': 'Foto de Perfil',
            'phone': 'Teléfono',
            'city': 'Ciudad',
            'country': 'País',
            'company': 'Empresa',
            'job_title': 'Cargo / Puesto',
            'user_type': 'Tipo de Usuario',
            'work_environment': 'Ambiente de Trabajo',
            'screen_size': 'Tamaño de Pantalla',
            'preferred_work_time': 'Horario de Trabajo Preferido',
            'notification_sound': 'Sonido de Notificación',
            'notification_sound_enabled': 'Habilitar Sonidos',
        }
        
        help_texts = {
            'first_name': 'Tu nombre (solo letras, espacios, apóstrofes y guiones, máx. 30 caracteres)',
            'last_name': 'Tu apellido (solo letras, espacios, apóstrofes y guiones, máx. 30 caracteres)',
            'bio': 'Cuéntanos brevemente sobre ti (máx. 500 caracteres)',
            'birth_date': 'Fecha de nacimiento para personalización de recomendaciones',
            'image': 'Imagen JPG, PNG o GIF (máx. 5MB). Se ajustará automáticamente.',
            'phone': 'Número telefónico con código de país (ej: +593 999 999 999)',
            'city': 'Ciudad donde trabajas habitualmente',
            'country': 'País de residencia',
            'company': 'Nombre de tu empresa u organización',
            'job_title': 'Tu cargo o rol laboral actual',
            'user_type': 'Selecciona el tipo que mejor describe tu uso',
            'work_environment': '¿Dónde trabajas principalmente?',
            'screen_size': 'Tamaño aproximado de tu pantalla principal',
            'preferred_work_time': '¿Cuándo sueles trabajar más?',
            'notification_sound': 'Elige el sonido para notificaciones importantes',
            'notification_sound_enabled': 'Activa/desactiva sonidos de notificación',
        }
        
        widgets = {
            'first_name': forms.TextInput(attrs={
                'maxlength': '30',
                'required': 'required',
                'autocomplete': 'given-name',
                'pattern': r"^[A-Za-zÀ-ÿ'\-\s]{1,30}$",
                'title': 'Solo letras, espacios, apóstrofes y guiones (máx. 30)',
                'placeholder': 'Ej: María José',
            }),
            'last_name': forms.TextInput(attrs={
                'maxlength': '30',
                'required': 'required',
                'autocomplete': 'family-name',
                'pattern': r"^[A-Za-zÀ-ÿ'\-\s]{1,30}$",
                'title': 'Solo letras, espacios, apóstrofes y guiones (máx. 30)',
                'placeholder': 'Ej: García López',
            }),
            'birth_date': forms.DateInput(attrs={
                'type': 'date',
                'max': timezone.now().date().isoformat(),
                'min': '1900-01-01',
            }),
            'bio': forms.Textarea(attrs={
                'rows': 3,
                'maxlength': '500',
                'placeholder': 'Cuéntanos sobre ti, tus intereses profesionales, tu experiencia...',
            }),
            'phone': forms.TextInput(attrs={
                'type': 'tel',
                'pattern': r"^[0-9()+\-\s]{6,20}$",
                'title': 'Solo dígitos, espacios, +, -, () (6-20 caracteres)',
                'placeholder': '+593 999 999 999',
                'autocomplete': 'tel',
            }),
            'country': forms.TextInput(attrs={
                'maxlength': '100',
                'placeholder': 'Ej: Ecuador',
                'autocomplete': 'country-name',
            }),
            'city': forms.TextInput(attrs={
                'maxlength': '200',
                'placeholder': 'Ej: Quito',
                'autocomplete': 'address-level2',
            }),
            'company': forms.TextInput(attrs={
                'maxlength': '200',
                'placeholder': 'Ej: VisionPulse Inc.',
                'autocomplete': 'organization',
            }),
            'job_title': forms.TextInput(attrs={
                'maxlength': '200',
                'placeholder': 'Ej: Desarrollador Full Stack',
                'autocomplete': 'organization-title',
            }),
            'notification_sound': forms.Select(),
            'notification_sound_enabled': forms.CheckboxInput(),
        }

    # -----------------
    # Server-side validation
    # -----------------
    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if not email:
            raise ValidationError('El correo electrónico es obligatorio.')
        
        # Validar formato básico
        if '@' not in email or '.' not in email.split('@')[-1]:
            raise ValidationError('Por favor ingresa un correo electrónico válido (ej: usuario@ejemplo.com).')
        
        # Verificar unicidad
        qs = User.objects.filter(email=email)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError('Este correo electrónico ya está registrado. Por favor usa otro.')
        return email

    def clean_first_name(self):
        fn = (self.cleaned_data.get('first_name') or '').strip()
        if not fn:
            raise ValidationError('El nombre es obligatorio.')
        if len(fn) > 30:
            raise ValidationError('El nombre no puede superar los 30 caracteres.')
        if not re.match(r"^[A-Za-zÀ-ÿ'\-\s]{1,30}$", fn):
            raise ValidationError('El nombre solo puede contener letras, espacios, apóstrofes y guiones.')
        return fn

    def clean_last_name(self):
        ln = (self.cleaned_data.get('last_name') or '').strip()
        if not ln:
            raise ValidationError('El apellido es obligatorio.')
        if len(ln) > 30:
            raise ValidationError('El apellido no puede superar los 30 caracteres.')
        if not re.match(r"^[A-Za-zÀ-ÿ'\-\s]{1,30}$", ln):
            raise ValidationError('El apellido solo puede contener letras, espacios, apóstrofes y guiones.')
        return ln

    def clean_birth_date(self):
        bd = self.cleaned_data.get('birth_date')
        if bd:
            today = timezone.now().date()
            if bd > today:
                raise ValidationError('La fecha de nacimiento no puede ser futura.')
            if bd.year < 1900:
                raise ValidationError('Por favor ingresa una fecha de nacimiento válida (posterior a 1900).')
            
            # Calcular edad
            age = today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))
            if age < 13:
                raise ValidationError('Debes tener al menos 13 años para usar VisionPulse.')
            if age > 120:
                raise ValidationError('Por favor verifica la fecha de nacimiento ingresada.')
        return bd

    def clean_phone(self):
        phone = (self.cleaned_data.get('phone') or '').strip()
        if phone:
            # Eliminar espacios para validar
            phone_clean = phone.replace(' ', '').replace('-', '')
            if len(phone_clean) < 6:
                raise ValidationError('El número telefónico es demasiado corto (mínimo 6 dígitos).')
            if len(phone) > 20:
                raise ValidationError('El número telefónico es demasiado largo (máximo 20 caracteres).')
            if not re.match(r"^[0-9()+\-\s]{6,20}$", phone):
                raise ValidationError('Formato de teléfono inválido. Usa solo dígitos, espacios, +, -, ().')
        return phone
    
    def clean_bio(self):
        bio = (self.cleaned_data.get('bio') or '').strip()
        if len(bio) > 500:
            raise ValidationError('La biografía no puede superar los 500 caracteres.')
        return bio
    
    def clean_image(self):
        image = self.cleaned_data.get('image')
        if image:
            # Validar tamaño (5MB máximo)
            if hasattr(image, 'size') and image.size > 5 * 1024 * 1024:
                raise ValidationError('La imagen no puede superar los 5MB.')
            
            # Validar formato
            if hasattr(image, 'content_type'):
                allowed_types = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
                if image.content_type not in allowed_types:
                    raise ValidationError('Formato no soportado. Usa JPG, PNG, GIF o WEBP.')
        return image

# Formulario de configuración/preferencias
class SettingsForm(forms.ModelForm):
    class Meta:
        model = UserMonitoringConfig
        fields = [
            'ear_threshold',
            'microsleep_duration_seconds',
            'low_blink_rate_threshold',
            'high_blink_rate_threshold',
            'low_light_threshold',
            'monitoring_frequency',
            'break_reminder_interval',
            'sampling_interval_seconds',
            'camera_enabled',
            # Nuevos tiempos de detección / resolución / repetición
            'detection_delay_seconds',
            'hysteresis_timeout_seconds',
            'alert_cooldown_seconds',
            'alert_repeat_interval',
            'repeat_max_per_hour',
            # UI / notificaciones / privacidad
            'dark_mode',
            'alert_volume',
            'notify_inactive_tab',
            'email_notifications',
            'data_collection_consent',
            'anonymous_analytics',
            'locale',
            'timezone'
        ]
        
        labels = {
            'ear_threshold': 'Umbral de Apertura Ocular (EAR)',
            'microsleep_duration_seconds': 'Duración Microsueño (seg)',
            'low_blink_rate_threshold': 'Umbral Parpadeo Bajo (por min)',
            'high_blink_rate_threshold': 'Umbral Parpadeo Alto (por min)',
            'low_light_threshold': 'Umbral Luz Baja',
            'monitoring_frequency': 'Frecuencia de Monitoreo (seg)',
            'break_reminder_interval': 'Recordatorio Descanso (min)',
            'sampling_interval_seconds': 'Intervalo de Muestreo (seg)',
            'camera_enabled': 'Cámara Habilitada',
            'detection_delay_seconds': 'Retraso Detección (seg)',
            'hysteresis_timeout_seconds': 'Tiempo Histéresis (seg)',
            'alert_cooldown_seconds': 'Intervalo entre Alertas (seg)',
            'alert_repeat_interval': 'Intervalo Repetición Alertas (seg)',
            'repeat_max_per_hour': 'Máximo Repeticiones por Hora',
            'alert_volume': 'Volumen de Alertas',
            'notify_inactive_tab': 'Notificar en Pestaña Inactiva',
            'email_notifications': 'Notificaciones por Email',
            'dark_mode': 'Modo Oscuro',
            'data_collection_consent': 'Recolección de Datos',
            'anonymous_analytics': 'Analíticas Anónimas',
            'locale': 'Idioma',
            'timezone': 'Zona Horaria',
        }
        
        help_texts = {
            'ear_threshold': 'Umbral de relación de aspecto ocular. Valores más bajos = más sensible a ojos cerrados (recomendado: 0.20)',
            'microsleep_duration_seconds': 'Tiempo que los ojos deben estar cerrados para detectar microsueño. Menor = más sensible (recomendado: 5.0)',
            'low_blink_rate_threshold': 'Parpadeos por minuto considerados anormalmente bajos. Indica resequedad ocular (recomendado: 10)',
            'high_blink_rate_threshold': 'Parpadeos por minuto considerados anormalmente altos. Puede indicar estrés visual (recomendado: 35)',
            'low_light_threshold': 'Nivel de luminancia considerado insuficiente. Valores más altos = más exigente (recomendado: 70)',
            'monitoring_frequency': 'Cada cuántos segundos se analizan las métricas visuales. Menor = más responsivo pero más CPU (recomendado: 30)',
            'break_reminder_interval': 'Cada cuántos minutos se te recordará tomar un descanso. Sigue la regla 20-20-20 (recomendado: 20)',
            'sampling_interval_seconds': 'Frecuencia de captura de frames de video. Menor = más preciso pero más CPU (recomendado: 5)',
            'camera_enabled': 'Activa/desactiva el acceso a la cámara para el monitoreo visual',
            'detection_delay_seconds': 'Segundos continuos en estado anormal antes de disparar una alerta. Evita falsos positivos (recomendado: 5)',
            'hysteresis_timeout_seconds': 'Segundos en estado normal necesarios para considerar una condición resuelta. Evita alertas intermitentes (recomendado: 30)',
            'alert_cooldown_seconds': 'Tiempo mínimo entre alertas del mismo tipo. Previene sobrecarga de notificaciones (recomendado: 60)',
            'alert_repeat_interval': 'Cada cuántos segundos se repite el sonido de una alerta no atendida (recomendado: 5)',
            'repeat_max_per_hour': 'Máximo número de veces que una alerta puede repetirse por hora. Previene saturación (recomendado: 12)',
            'alert_volume': 'Nivel de volumen para alertas sonoras. 0.0 = silencio, 1.0 = volumen máximo (recomendado: 0.5)',
            'notify_inactive_tab': 'Recibe notificaciones del navegador cuando VisionPulse no es la pestaña activa',
            'email_notifications': 'Recibe resúmenes y alertas importantes por correo electrónico',
            'dark_mode': 'Activa el tema oscuro de la interfaz, ideal para ambientes con poca luz',
            'data_collection_consent': 'Autoriza la recolección de datos para mejorar el servicio. Puedes revocar en cualquier momento',
            'anonymous_analytics': 'Comparte datos anónimos de uso para ayudarnos a mejorar VisionPulse',
            'locale': 'Idioma de la interfaz (ej: es-ES para español)',
            'timezone': 'Tu zona horaria para estadísticas precisas (ej: America/Guayaquil)',
        }
        
        widgets = {
            'ear_threshold': forms.NumberInput(attrs={'step': '0.01', 'min': 0.05, 'max': 0.40}),
            'microsleep_duration_seconds': forms.NumberInput(attrs={'step': '0.5', 'min': 5.0, 'max': 15.0}),
            'low_blink_rate_threshold': forms.NumberInput(attrs={'min': 3, 'max': 20}),
            'high_blink_rate_threshold': forms.NumberInput(attrs={'min': 25, 'max': 60}),
            'low_light_threshold': forms.NumberInput(attrs={'min': 30, 'max': 120}),
            'monitoring_frequency': forms.NumberInput(attrs={'min': 10, 'max': 300}),
            'break_reminder_interval': forms.NumberInput(attrs={'min': 5, 'max': 120}),
            'sampling_interval_seconds': forms.NumberInput(attrs={'min': 1, 'max': 60}),
            'detection_delay_seconds': forms.NumberInput(attrs={'min': 1, 'max': 3600}),
            'hysteresis_timeout_seconds': forms.NumberInput(attrs={'min': 5, 'max': 3600}),
            'alert_cooldown_seconds': forms.NumberInput(attrs={'min': 5, 'max': 3600}),
            'alert_repeat_interval': forms.NumberInput(attrs={'min': 1, 'max': 50}),
            'repeat_max_per_hour': forms.NumberInput(attrs={'min': 1, 'max': 60}),
            'alert_volume': forms.NumberInput(attrs={'step': '0.01', 'min': 0.0, 'max': 1.0}),
            'locale': forms.TextInput(attrs={'maxlength': 10, 'placeholder': 'es-ES'}),
            'timezone': forms.TextInput(attrs={'maxlength': 50, 'placeholder': 'America/Guayaquil'}),
        }

    # Validaciones específicas (se refuerzan los validators del modelo para feedback inmediato)
    def clean_ear_threshold(self):
        v = self.cleaned_data['ear_threshold']
        if not (0.05 <= v <= 0.40):
            raise ValidationError(f'El umbral EAR debe estar entre 0.05 y 0.40 (valor ingresado: {v})')
        return v

    def clean_microsleep_duration_seconds(self):
        v = self.cleaned_data['microsleep_duration_seconds']
        if not (5.0 <= v <= 15.0):
            raise ValidationError(f'La duración de microsueño debe estar entre 5.0 y 15.0 segundos (valor ingresado: {v})')
        return v

    def clean_low_blink_rate_threshold(self):
        v = self.cleaned_data['low_blink_rate_threshold']
        if not (3 <= v <= 20):
            raise ValidationError(f'El umbral de parpadeo bajo debe estar entre 3 y 20 (valor ingresado: {v})')
        return v

    def clean_high_blink_rate_threshold(self):
        v = self.cleaned_data['high_blink_rate_threshold']
        if not (25 <= v <= 60):
            raise ValidationError(f'El umbral de parpadeo alto debe estar entre 25 y 60 (valor ingresado: {v})')
        return v
    
    def clean_low_light_threshold(self):
        v = self.cleaned_data.get('low_light_threshold')
        if v is not None and not (30 <= v <= 120):
            raise ValidationError(f'El umbral de luz baja debe estar entre 30 y 120 (valor ingresado: {v})')
        return v
    
    def clean_monitoring_frequency(self):
        v = self.cleaned_data.get('monitoring_frequency')
        if v is not None and not (10 <= v <= 300):
            raise ValidationError(f'La frecuencia de monitoreo debe estar entre 10 y 300 segundos (valor ingresado: {v})')
        return v
    
    def clean_break_reminder_interval(self):
        v = self.cleaned_data.get('break_reminder_interval')
        if v is not None and not (5 <= v <= 120):
            raise ValidationError(f'El intervalo de recordatorio debe estar entre 5 y 120 minutos (valor ingresado: {v})')
        return v

    def clean_detection_delay_seconds(self):
        v = self.cleaned_data['detection_delay_seconds']
        if not (1 <= v <= 3600):
            raise ValidationError(f'El retraso de detección debe estar entre 1 y 3600 segundos (valor ingresado: {v})')
        return v

    def clean_hysteresis_timeout_seconds(self):
        v = self.cleaned_data['hysteresis_timeout_seconds']
        if not (5 <= v <= 3600):
            raise ValidationError(f'El tiempo de histéresis debe estar entre 5 y 3600 segundos (valor ingresado: {v})')
        return v

    def clean_alert_cooldown_seconds(self):
        v = self.cleaned_data['alert_cooldown_seconds']
        if not (5 <= v <= 3600):
            raise ValidationError(f'El cooldown de alertas debe estar entre 5 y 3600 segundos (valor ingresado: {v})')
        return v
    
    def clean_alert_repeat_interval(self):
        v = self.cleaned_data.get('alert_repeat_interval')
        if v is not None and not (1 <= v <= 50):
            raise ValidationError(f'El intervalo de repetición debe estar entre 1 y 50 segundos (valor ingresado: {v})')
        return v
    
    def clean_repeat_max_per_hour(self):
        v = self.cleaned_data.get('repeat_max_per_hour')
        if v is not None and not (1 <= v <= 60):
            raise ValidationError(f'El máximo de repeticiones debe estar entre 1 y 60 por hora (valor ingresado: {v})')
        return v
    
    def clean_alert_volume(self):
        v = self.cleaned_data.get('alert_volume')
        if v is not None and not (0.0 <= v <= 1.0):
            raise ValidationError(f'El volumen debe estar entre 0.0 y 1.0 (valor ingresado: {v})')
        return v

    def clean(self):
        data = super().clean()
        low_blink = data.get('low_blink_rate_threshold')
        high_blink = data.get('high_blink_rate_threshold')
        if low_blink and high_blink and low_blink >= high_blink:
            raise ValidationError({
                'high_blink_rate_threshold': f'El umbral de parpadeo alto ({high_blink}) debe ser mayor que el umbral bajo ({low_blink})'
            })
        
        # Validar que detection_delay no sea excesivamente alto comparado con hysteresis
        delay = data.get('detection_delay_seconds')
        hyst = data.get('hysteresis_timeout_seconds')
        if delay and hyst and delay > hyst:
            self.add_error('detection_delay_seconds', 
                f'El retraso de detección ({delay}s) no debería ser mayor que el tiempo de histéresis ({hyst}s) para un funcionamiento óptimo.')
        
        return data
