import json
from channels.generic.websocket import AsyncWebsocketConsumer

class AlertConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Conectarse al grupo de alertas del usuario
        await self.channel_layer.group_add(
            f"user_alerts_{self.scope['user'].id}",
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        # Desconectarse del grupo de alertas
        await self.channel_layer.group_discard(
            f"user_alerts_{self.scope['user'].id}",
            self.channel_name
        )

    async def receive(self, text_data):
        # Procesar mensajes recibidos del WebSocket (si es necesario)
        pass

    async def alert_message(self, event):
        # Enviar mensaje de alerta al WebSocket
        message = event['message']
        await self.send(text_data=json.dumps(message))