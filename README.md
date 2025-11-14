# VisionPulse 👁️

Sistema inteligente de monitoreo visual y ergonómico para mejorar la salud y productividad en el trabajo frente a pantallas.

## 📋 Descripción

VisionPulse es una aplicación web desarrollada con Django que utiliza visión por computadora y machine learning para monitorear en tiempo real la salud visual y postural de usuarios que trabajan frente a pantallas. El sistema detecta patrones de fatiga, postura incorrecta, distancia inadecuada y otros factores de riesgo, proporcionando alertas inteligentes y recomendaciones personalizadas para prevenir problemas de salud relacionados con el uso prolongado de dispositivos digitales.

## ✨ Características Principales

### 🎯 Monitoreo en Tiempo Real
- **Detección de parpadeo**: Análisis continuo de la frecuencia de parpadeo para prevenir fatiga visual
- **Análisis de postura**: Monitoreo de posición de cabeza y cuello para detectar malas posturas
- **Medición de distancia**: Control de la distancia óptima entre usuario y pantalla
- **Detección de distracciones**: Identificación de pérdida de foco y ausencia del puesto de trabajo

### 🔔 Sistema de Alertas Inteligente
- **11 tipos de alertas diferentes**: Desde recordatorios de descanso hasta detección de microsueño
- **Alertas visuales y sonoras**: Notificaciones personalizables según nivel de severidad
- **Filtrado inteligente**: Solo muestra alertas relevantes (≥1% del total)
- **Clasificación por prioridad**: Sistema de colores para identificar rápidamente alertas críticas

### 📊 Dashboard y Reportes
- **Métricas en tiempo real**: Visualización de indicadores clave durante sesiones activas
- **Historial de sesiones**: Registro completo de todas las sesiones de monitoreo
- **Gráficos interactivos**: Distribución de alertas, tendencias de parpadeo y foco promedio
- **Exportación de reportes**: Generación de reportes detallados en múltiples formatos
- **Modo oscuro completo**: Interfaz optimizada para trabajar en entornos de baja luz

### 👥 Gestión de Usuarios
- **Sistema de autenticación seguro**: Login con control de sesiones
- **Roles y permisos**: Administración granular de accesos
- **Perfiles personalizados**: Configuración individual de preferencias y umbrales
- **Gestión de grupos**: Organización de usuarios por departamentos o equipos

### ⚙️ Configuración Avanzada
- **Umbrales personalizables**: Ajuste de sensibilidad para cada tipo de alerta
- **Intervalos de descanso**: Configuración de recordatorios de pausas
- **Preferencias de notificación**: Control de sonidos, visuales y frecuencia
- **Calibración de cámara**: Ajuste de parámetros de detección según hardware

## 🛠️ Tecnologías

### Backend
- **Django 5.x**: Framework web principal
- **Django REST Framework**: API RESTful para comunicación con frontend
- **Django Channels**: WebSockets para actualizaciones en tiempo real
- **PostgreSQL**: Base de datos relacional
- **Redis**: Cache y manejo de sesiones en tiempo real
- **OpenCV**: Procesamiento de visión por computadora
- **MediaPipe**: Detección de puntos faciales y seguimiento

### Frontend
- **HTML5 + CSS3**: Estructura y estilos
- **TailwindCSS**: Framework de utilidades CSS
- **JavaScript (ES6+)**: Lógica del cliente
- **Chart.js**: Visualización de datos
- **Font Awesome**: Iconografía
- **HTMX**: Interactividad reactiva

### Infraestructura
- **Docker**: Contenedorización (opcional)
- **Nginx**: Servidor web de producción
- **Gunicorn**: Servidor WSGI
- **Git**: Control de versiones

## 📦 Instalación

### Prerrequisitos
- Python 3.10+
- Node.js 16+
- PostgreSQL 14+
- Redis 6+
- Cámara web

### Configuración del Entorno

1. **Clonar el repositorio**
```bash
git clone https://github.com/surgiSkate11/VisionPulse.git
cd VisionPulse
```

2. **Crear entorno virtual**
```bash
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate
```

3. **Instalar dependencias de Python**
```bash
pip install -r requirements.txt
```

4. **Instalar dependencias de frontend**
```bash
cd frontend
npm install
npm run build
cd ..
```

5. **Configurar variables de entorno**
```bash
cp .env.example .env
# Editar .env con tus configuraciones
```

6. **Ejecutar migraciones**
```bash
python manage.py migrate
```

7. **Crear superusuario**
```bash
python manage.py createsuperuser
```

8. **Recolectar archivos estáticos**
```bash
python manage.py collectstatic --noinput
```

9. **Iniciar servidor de desarrollo**
```bash
python manage.py runserver
```

10. **Acceder a la aplicación**
```
http://localhost:8000
```

## 🚀 Uso

### Iniciar una Sesión de Monitoreo

1. Inicia sesión con tu usuario
2. Ve a la sección "Monitoreo en Vivo"
3. Permite el acceso a la cámara cuando se solicite
4. Haz clic en "Iniciar Monitoreo"
5. El sistema comenzará a analizar tu postura, parpadeo y distancia
6. Recibirás alertas cuando se detecten problemas

### Configurar Alertas

1. Ve a "Configuración"
2. Ajusta los umbrales de cada tipo de alerta
3. Configura intervalos de descanso
4. Personaliza sonidos y notificaciones visuales
5. Guarda los cambios

### Generar Reportes

1. Ve a "Reportes"
2. Selecciona el rango de fechas
3. Filtra por tipo de alerta o sesión
4. Visualiza gráficos y estadísticas
5. Exporta en PDF, Excel o CSV

## 📊 Estructura del Proyecto

```
VisionPulse/
├── apps/
│   ├── core/              # Funcionalidades base
│   ├── exercises/         # Ejercicios de descanso visual
│   ├── monitoring/        # Sistema de monitoreo en tiempo real
│   ├── reports/           # Generación de reportes y dashboard
│   └── security/          # Autenticación y permisos
├── frontend/
│   ├── src/
│   │   └── styles.css     # Estilos Tailwind
│   ├── package.json
│   └── tailwind.config.js
├── media/                 # Archivos multimedia
├── static/                # Archivos estáticos
├── templates/             # Templates HTML
├── visionpulse/          # Configuración Django
├── manage.py
├── requirements.txt
└── README.md
```

## 🎨 Tipos de Alertas

- **Fatiga Visual**: Detección de ojos cansados o rojos
- **Distracción**: Usuario no mirando la pantalla
- **Luz Baja**: Iluminación insuficiente en el ambiente
- **Microsueño**: Detección de cierre prolongado de ojos
- **Parpadeo Bajo**: Frecuencia de parpadeo inferior a lo normal
- **Parpadeo Alto**: Parpadeo excesivo que indica fatiga
- **Distracción Frecuente**: Pérdida de foco reiterada
- **Uso de Celular**: Detección de distracción con dispositivo móvil
- **Rigidez Postural**: Falta de movimiento corporal
- **Movimiento de Cabeza**: Agitación excesiva de la cabeza
- **Usuario Ausente**: Detección de ausencia del puesto
- **Múltiples Personas**: Más de una persona detectada
- **Cámara Obstruida**: Bloqueo parcial de la cámara
- **Cámara Perdida**: Pérdida total de señal de cámara
- **Tensión de Cuello**: Postura forzada del cuello
- **Somnolencia**: Patrón de micro-ritmos indicando sueño
- **Mala Postura**: Posición corporal incorrecta
- **Distancia Incorrecta**: Usuario muy cerca o muy lejos
- **Reflejo**: Brillo excesivo en pantalla
- **Luz Excesiva**: Iluminación muy intensa
- **Recordatorio de Descanso**: Alerta programada para pausas

## 🔒 Seguridad

- Autenticación basada en sesiones de Django
- Protección CSRF en todos los formularios
- Validación de permisos en cada vista
- Encriptación de contraseñas con PBKDF2
- Control de acceso basado en roles
- Logs de auditoría de acciones críticas

## 🤝 Contribución

¡Las contribuciones son bienvenidas! Por favor:

1. Fork el proyecto
2. Crea una rama para tu feature (`git checkout -b feature/AmazingFeature`)
3. Commit tus cambios (`git commit -m 'Add some AmazingFeature'`)
4. Push a la rama (`git push origin feature/AmazingFeature`)
5. Abre un Pull Request

## 📝 Licencia

Este proyecto está bajo la Licencia MIT. Ver el archivo `LICENSE` para más detalles.

## 👥 Autores

- **DayBu** - *Desarrollo principal* - [surgiSkate11](https://github.com/surgiSkate11)

## 🙏 Agradecimientos

- OpenCV y MediaPipe por las bibliotecas de visión por computadora
- Django community por el excelente framework
- TailwindCSS por el sistema de diseño
- Todos los contribuidores y testers

## 📧 Contacto

Para soporte o consultas, por favor abre un issue en GitHub o contacta al equipo de desarrollo.

---

⚡ **VisionPulse** - Cuida tu salud visual mientras trabajas
