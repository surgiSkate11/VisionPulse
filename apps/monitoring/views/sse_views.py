from time import sleep
from django.http import StreamingHttpResponse
from django.contrib.auth.decorators import login_required
import json
import logging

logger = logging.getLogger(__name__)

@login_required
def alert_stream(request):
    """Stream de eventos para alertas usando Server-Sent Events (SSE)"""
    def event_stream():
        while True:
            # Intentar obtener la siguiente alerta
            try:
                from .alert_views import get_next_alert
                response = get_next_alert(request)
                data = json.loads(response.content)
                
                if data.get('status') == 'success' and data.get('alert'):
                    # Formatear el evento SSE
                    alert_data = json.dumps(data['alert'])
                    yield f"data: {alert_data}\n\n"
                    logger.info(f"[SSE] Enviada alerta: {data['alert'].get('id')}")
            except Exception as e:
                logger.error(f"[SSE] Error en stream: {e}")
            
            # Esperar antes de la siguiente verificación
            sleep(1)

    response = StreamingHttpResponse(
        event_stream(),
        content_type='text/event-stream'
    )
    response['Cache-Control'] = 'no-cache'
    # Removemos el header Connection ya que causa problemas con WSGI
    response['X-Accel-Buffering'] = 'no'
    return response