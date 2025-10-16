// Service Worker para monitoreo
const CACHE_NAME = 'vision-pulse-v1';
let activeSession = null;
let sendingFrames = false;

self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(clients.claim());
});

// Manejar mensajes desde la página
self.addEventListener('message', (event) => {
  const { type, data } = event.data;
  
  switch (type) {
    case 'START_SESSION':
      activeSession = data.sessionId;
      sendingFrames = true;
      // Notificar a todas las ventanas que el monitoreo está activo
      notifyAllClients({ type: 'SESSION_STATUS', data: { active: true, sessionId: activeSession } });
      break;
    
    case 'PAUSE_SESSION':
      sendingFrames = !sendingFrames;
      notifyAllClients({ type: 'SESSION_STATUS', data: { active: true, paused: !sendingFrames, sessionId: activeSession } });
      break;
    
    case 'STOP_SESSION':
      if (activeSession) {
        fetch('/monitoring/api/stop/', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': data.csrfToken
          },
          body: JSON.stringify({ session_id: activeSession })
        }).then(() => {
          activeSession = null;
          sendingFrames = false;
          notifyAllClients({ type: 'SESSION_STATUS', data: { active: false, sessionId: null } });
        });
      }
      break;
    
    case 'UPLOAD_FRAME':
      if (activeSession && sendingFrames) {
        fetch('/monitoring/api/upload_frame/', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': data.csrfToken
          },
          body: JSON.stringify({
            session_id: activeSession,
            image: data.frame
          })
        })
        .then(r => r.json())
        .then(response => {
          notifyAllClients({ 
            type: 'METRICS_UPDATE', 
            data: { 
              ear: response.avg_ear,
              blinks: response.total_blinks
            }
          });
        });
      }
      break;

    case 'CHECK_STATUS':
      // Responder con el estado actual
      event.source.postMessage({
        type: 'SESSION_STATUS',
        data: { 
          active: !!activeSession, 
          paused: !sendingFrames,
          sessionId: activeSession
        }
      });
      break;
  }
});

// Función helper para notificar a todos los clientes
async function notifyAllClients(message) {
  const clients = await self.clients.matchAll();
  clients.forEach(client => {
    client.postMessage(message);
  });
}