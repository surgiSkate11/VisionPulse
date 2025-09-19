from django.conf import settings
from django.db import models
from django.utils import timezone


class ReportRequest(models.Model):
    """
    Solicitud de reporte por el usuario. Se procesará asíncronamente (Celery/RQ).
    """
    STATUS_PENDING = 'pending'
    STATUS_PROCESSING = 'processing'
    STATUS_READY = 'ready'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pendiente'),
        (STATUS_PROCESSING, 'Procesando'),
        (STATUS_READY, 'Listo'),
        (STATUS_FAILED, 'Error'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='report_requests')
    requested_at = models.DateTimeField(default=timezone.now)
    period_from = models.DateTimeField(null=True, blank=True)
    period_to = models.DateTimeField(null=True, blank=True)
    params = models.JSONField(null=True, blank=True, help_text="Filtros y agregaciones")
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_PENDING)
    result_file = models.FileField(upload_to='reports/', null=True, blank=True)
    error_message = models.TextField(blank=True, null=True)
    task_id = models.CharField(max_length=255, null=True, blank=True, help_text="ID del worker (celery/rq)")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-requested_at']
        indexes = [models.Index(fields=['user', 'status', 'requested_at'])]
        verbose_name = 'Solicitud de Reporte'
        verbose_name_plural = 'Solicitudes de Reporte'

    def mark_processing(self, task_id: str = None):
        self.status = self.STATUS_PROCESSING
        if task_id:
            self.task_id = task_id
        self.save(update_fields=['status', 'task_id'])

    def mark_ready(self, file_field):
        self.result_file = file_field
        self.status = self.STATUS_READY
        self.save(update_fields=['result_file', 'status'])

    def mark_failed(self, error_message: str):
        self.error_message = error_message
        self.status = self.STATUS_FAILED
        self.save(update_fields=['error_message', 'status'])

    def __str__(self):
        return f"ReportRequest {self.id} ({self.user.username}) - {self.status}"


class ReportCache(models.Model):
    """
    Cache para reportes pesados que se pueden reutilizar.
    """
    key = models.CharField(max_length=200, unique=True)
    generated_at = models.DateTimeField(default=timezone.now)
    file = models.FileField(upload_to='reports/cache/')
    metadata = models.JSONField(null=True, blank=True)

    class Meta:
        verbose_name = 'Cache de Reporte'
        verbose_name_plural = 'Caches de Reporte'
        ordering = ['-generated_at']

    def __str__(self):
        return f"Cache {self.key} @ {self.generated_at:%Y-%m-%d}"


# =========================
# MODELOS TRANSVERSALES PARA AUDITORÍA Y COMPLIANCE
# =========================

class AuditLog(models.Model):
    """
    Registro de acciones administrativas o críticas para auditoría.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=150)
    target = models.CharField(max_length=200, null=True, blank=True)
    detail = models.JSONField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [models.Index(fields=['user', 'timestamp'])]
        verbose_name = 'Log de Auditoría'
        verbose_name_plural = 'Logs de Auditoría'

    def __str__(self):
        return f"{self.action} by {self.user} @ {self.timestamp:%Y-%m-%d %H:%M}"


class DataErasureRequest(models.Model):
    """
    Peticiones GDPR / derecho al olvido: trackear y procesar borrados/exportaciones.
    """
    STATUS_PENDING = 'pending'
    STATUS_PROCESSING = 'processing'
    STATUS_DONE = 'done'
    STATUS_CHOICES = [(STATUS_PENDING, 'Pendiente'), (STATUS_PROCESSING, 'Procesando'), (STATUS_DONE, 'Finalizado')]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    requested_at = models.DateTimeField(default=timezone.now)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_PENDING)
    processed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ['-requested_at']
        verbose_name = 'Solicitud de Borrado de Datos'
        verbose_name_plural = 'Solicitudes de Borrado de Datos'

    def mark_done(self):
        self.status = self.STATUS_DONE
        self.processed_at = timezone.now()
        self.save(update_fields=['status', 'processed_at'])

    def __str__(self):
        return f"DataErasure {self.user.username} - {self.status}"
