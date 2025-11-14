// Evitar redeclaración global
(function() {

// Configuraciones globales
window.ALERT_STYLES = {
    'critical': {
        borderColor: 'bg-red-500',
        icon: 'fas fa-exclamation-triangle',
        iconColor: 'text-red-500',
        pulse: true
    },
    'high': {
        borderColor: 'bg-orange-500',
        icon: 'fas fa-exclamation-circle',
        iconColor: 'text-orange-500',
        pulse: true
    },
    'medium': {
        borderColor: 'bg-yellow-500',
        icon: 'fas fa-exclamation',
        iconColor: 'text-yellow-500'
    },
    'low': {
        borderColor: 'bg-blue-500',
        icon: 'fas fa-info-circle',
        iconColor: 'text-blue-500'
    }
};

// Gestor de Audio para Alertas
class AlertAudioManager {
    constructor(config = {}) {
        this.audioContext = null;
        this.gainNode = null;
        this.currentSource = null;
        
        // Configurar volumen desde las preferencias del usuario
        this.volume = typeof config.alert_volume === 'number' ? config.alert_volume : 0.7;
        
        // Respetar la configuración de sonido habilitado del usuario
        this.soundEnabled = typeof config.notification_sound_enabled === 'boolean' 
            ? config.notification_sound_enabled 
            : true;
        
        this.initialize();
    }

    async initialize() {
        try {
            this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
            this.gainNode = this.audioContext.createGain();
            this.gainNode.connect(this.audioContext.destination);
            this.setVolume(this.volume);
        } catch (error) {
            console.error('[AUDIO] Error inicializando AudioContext:', error);
        }
    }

    setVolume(value) {
        this.volume = Math.max(0, Math.min(1, value));
        if (this.gainNode) {
            this.gainNode.gain.value = this.volume;
        }
    }

    setSoundEnabled(enabled) {
        this.soundEnabled = enabled;
        console.log('[AUDIO] Sonido de alertas:', enabled ? 'HABILITADO' : 'DESHABILITADO');
    }

    async playAlert(alert) {
        // RESPETAR EL CHECKBOX: Si el sonido está deshabilitado, no reproducir
        if (!this.soundEnabled) {
            console.log('[AUDIO] Sonido deshabilitado por preferencia del usuario');
            return { duration: 0 };
        }

        if (!alert || !alert.voice_clip) {
            console.warn('[AUDIO] Alerta sin clip de voz');
            return { duration: 0 };
        }

        try {
            const response = await fetch(alert.voice_clip);
            if (!response.ok) throw new Error('No se pudo cargar el audio');

            const arrayBuffer = await response.arrayBuffer();
            const audioBuffer = await this.audioContext.decodeAudioData(arrayBuffer);

            if (this.currentSource) {
                try {
                    this.currentSource.stop();
                } catch (_) {}
            }

            const source = this.audioContext.createBufferSource();
            source.buffer = audioBuffer;
            source.connect(this.gainNode);
            
            // Fade in suave
            this.gainNode.gain.setValueAtTime(0, this.audioContext.currentTime);
            this.gainNode.gain.linearRampToValueAtTime(this.volume, this.audioContext.currentTime + 0.1);
            
            source.start(0);
            this.currentSource = source;

            // Retornar la duración del audio en milisegundos
            const durationMs = audioBuffer.duration * 1000;
            return { duration: durationMs };

        } catch (error) {
            console.error('[AUDIO] Error reproduciendo audio:', error);
            // Fallback a elemento Audio HTML
            try {
                const audio = new Audio(alert.voice_clip);
                audio.volume = this.volume;
                await audio.play();
                this.currentSource = audio;
                // Estimar duración para fallback (típicamente 2-3 segundos)
                return { duration: 3000 };
            } catch (fallbackError) {
                console.error('[AUDIO] Error en fallback:', fallbackError);
                return { duration: 0 };
            }
        }
    }

    stop() {
        if (this.currentSource) {
            try {
                if (this.currentSource instanceof AudioBufferSourceNode) {
                    // Fade out suave
                    this.gainNode.gain.linearRampToValueAtTime(0, this.audioContext.currentTime + 0.1);
                    setTimeout(() => {
                        try {
                            this.currentSource.stop();
                        } catch (_) {}
                    }, 100);
                } else if (this.currentSource instanceof HTMLAudioElement) {
                    this.currentSource.pause();
                    this.currentSource.currentTime = 0;
                }
            } catch (e) {
                console.warn('[AUDIO] Error al detener audio:', e);
            }
        }
        this.currentSource = null;
    }

    clearAllRepeats() {
        this.stop();
        if (this._repeatTimer) {
            clearInterval(this._repeatTimer);
            this._repeatTimer = null;
        }
    }
}

// Asignar AudioManager al objeto window
if (typeof window.AlertAudioManager === 'undefined') {
    window.AlertAudioManager = AlertAudioManager;
}

if (typeof window.AlertNotificationManager === 'undefined') {

// Clase AlertNotificationManager: Gestiona las notificaciones de alerta con reglas avanzadas
class AlertNotificationManager {
    constructor() {
        console.log('[ALERT] Inicializando AlertNotificationManager...');
        this.container = document.getElementById('alert-container');
        this.template = document.getElementById('alert-template');
        this.activeAlerts = new Map(); // Mapa de alertas activas: ID -> {element, config}
        this.alertConfigs = new Map(); // Cache de configuraciones: tipo -> {maxReps, interval, etc}
        this.audioManager = new AlertAudioManager(); // Gestor de audio
        this.darkMode = document.documentElement.classList.contains('dark');
        
        // Propiedades para compatibilidad con el HTML
        this.currentAlertId = null;
        this.currentAlertType = null;
        this.suppressedTypes = new Map(); // Para suprimir tipos de alertas temporalmente
        
        // Rastrear alertas esperando su detection_delay
        this.alertsWaitingForDelay = new Map(); // id -> { type, timestamp, delayMs }

        // Binding de métodos
        this.showAlert = this.showAlert.bind(this);
        this.closeAlert = this.closeAlert.bind(this);
        this.handleExerciseClick = this.handleExerciseClick.bind(this);

        // Inicializar eventos
        this.initializeEventListeners();
    }

    initializeEventListeners() {
        // Escuchar cambios en modo oscuro
        const observer = new MutationObserver((mutations) => {
            mutations.forEach((mutation) => {
                if (mutation.attributeName === 'class') {
                    this.darkMode = document.documentElement.classList.contains('dark');
                    this.updateAllAlertStyles();
                }
            });
        });
        observer.observe(document.documentElement, { attributes: true });

        // 🔥 NO conectar EventSource automáticamente al cargar
        // Se conectará cuando inicie el monitoreo
        console.log('[ALERT] EventListeners inicializados (EventSource en espera)');
    }

    setupEventSource() {
        // Verificar si ya tenemos una conexión activa
        if (this.evtSource && this.evtSource.readyState !== EventSource.CLOSED) {
            console.log('[ALERT] EventSource ya está conectado, reutilizando');
            return;
        }
        
        const evtSource = new EventSource('/monitoring/api/alerts/stream/');
        
        console.log('[ALERT] Conectando EventSource...');
        
        evtSource.onopen = () => {
            console.log('[ALERT] ✅ EventSource conectado correctamente');
        };
        
        evtSource.onmessage = (event) => {
            try {
                console.log('[ALERT] 📨 Mensaje SSE recibido RAW:', event.data);
                const data = JSON.parse(event.data);
                console.log('[ALERT] 📦 Datos parseados:', data);
                
                // Validar que los datos tengan ID válido
                if (!data || !data.id) {
                    console.warn('[ALERT] ⚠️ Mensaje SSE sin ID, ignorando:', data);
                    return;
                }
                
                this.processAlert(data);
            } catch (error) {
                console.error('[ALERT] Error procesando mensaje:', error, 'Data:', event.data);
            }
        };

        evtSource.onerror = (error) => {
            console.error('[ALERT] ⚠️ Error en EventSource:', error);
            
            // 🔥 NO RECONECTAR si el EventSource fue cerrado intencionalmente
            if (this.evtSource === null) {
                console.log('[ALERT] EventSource fue cerrado intencionalmente, NO reconectar');
                evtSource.close();
                return;
            }
            
            // Reconexión automática solo si está en estado de error
            if (evtSource.readyState === EventSource.CLOSED) {
                console.log('[ALERT] 🔄 Intentando reconexión en 5s...');
                setTimeout(() => {
                    // Verificar nuevamente que no se haya cerrado intencionalmente
                    if (this.evtSource !== null) {
                        this.setupEventSource();
                    } else {
                        console.log('[ALERT] Reconexión cancelada (EventSource cerrado intencionalmente)');
                    }
                }, 5000);
            }
        };

        this.evtSource = evtSource;
    }

    // Procesa una nueva alerta recibida
    async processAlert(alertData) {
        if (!alertData) {
            console.log('[ALERT] alertData vacío, ignorando');
            return false;
        }
        
        const { id, type, message, metadata = {} } = alertData;
        
        console.log('[ALERT] processAlert() llamado con:', { id, type, message, metadata });
        console.log('[ALERT] 🏋️ ¿Tiene ejercicio en alertData?', alertData.exercise ? 'SÍ' : 'NO', alertData.exercise);
        console.log('[ALERT] 🏋️ ¿Tiene ejercicio en metadata?', metadata.exercise ? 'SÍ' : 'NO', metadata.exercise);
        console.log('[ALERT] 📦 alertData completo:', alertData);

        // 🔥 CRÍTICO: NO procesar alertas si no hay sesión activa O si está pausada
        // Verificar si el monitoreo está activo y NO pausado
        if (typeof window.isMonitoringActive !== 'undefined' && !window.isMonitoringActive) {
            console.log('[ALERT] ⚠️ Monitoreo inactivo, ignorando alerta:', type);
            return false;
        }
        
        // 🔥 CRÍTICO: NO procesar alertas si la sesión está PAUSADA
        if (typeof window.isPaused !== 'undefined' && window.isPaused) {
            console.log('[ALERT] ⏸️ Sesión pausada, ignorando alerta:', type);
            return false;
        }

        // 🔥 VALIDACIÓN CRÍTICA: Si ID es undefined o null, RECHAZAR
        // Solo procesar alertas con ID válido del backend
        if (!id || id === 'undefined' || id === null) {
            console.log('[ALERT] ⚠️ ID inválido o undefined, esperando ID real del backend:', { id, type });
            return false;
        }

        // Si la alerta ya existe, actualizar según reglas
        if (this.activeAlerts.has(id)) {
            console.log('[ALERT] Alerta ya existe, actualizando:', id);
            return this.updateExistingAlert(id, alertData);
        }

        // ========== LÓGICA DE DETECTION_DELAY ==========
        // Para alertas críticas, verificar si el backend ya cumplió el detection_delay
        const isCriticalAlert = ['driver_absent', 'multiple_people', 'camera_occluded'].includes(type);
        const detectionTime = metadata.detection_time || 0;
        const detectionDelay = metadata.detection_delay !== undefined ? metadata.detection_delay :
                               (window.MONITORING_CONFIG?.detection_delay_seconds || 5);
        
        // Si detection_delay es 0, significa que el motor ya manejó el tiempo (ej: camera_occluded)
        // En ese caso, mostrar la alerta inmediatamente
        if (isCriticalAlert && detectionDelay > 0 && detectionTime < detectionDelay) {
            // El backend aún NO ha cumplido el detection_delay configurado
            // NO mostrar alerta todavía - el backend seguirá enviando actualizaciones
            const remainingTime = (detectionDelay - detectionTime).toFixed(1);
            console.log(`[ALERT] ⏱️ Alerta crítica esperando delay: ${type}, faltan ${remainingTime}s de ${detectionDelay}s configurados`);
            
            // Registrar en el mapa para tracking (sin setTimeout)
            if (!this.alertsWaitingForDelay.has(id)) {
                this.alertsWaitingForDelay.set(id, {
                    type,
                    firstSeen: Date.now(),
                    alertData,
                    detectionTime,
                    detectionDelay
                });
                console.log(`[ALERT] 📋 Registrando alerta ${id} en espera (${remainingTime}s restantes)`);
            }
            
            // NO procesar la alerta todavía
            return false;
        }
        
        // Si llegamos aquí con una alerta crítica, significa que detection_time >= detection_delay
        // Limpiar del mapa de espera si estaba registrada
        if (isCriticalAlert && this.alertsWaitingForDelay.has(id)) {
            const waitInfo = this.alertsWaitingForDelay.get(id);
            const waitedMs = Date.now() - waitInfo.firstSeen;
            console.log(`[ALERT] ✓ Delay completado para ${type} (esperó ${waitedMs}ms, detection_time: ${detectionTime}s)`);
            this.alertsWaitingForDelay.delete(id);
        }

        // Obtener configuración de este tipo de alerta (con fallback seguro)
        let config = null;
        try {
            config = await this.getAlertConfig(type);
            console.log('[ALERT] Configuración obtenida:', { type, config });
        } catch (error) {
            console.error('[ALERT] Error obteniendo configuración, usando defaults:', error);
            // Usar configuración por defecto si falla
            config = {
                title: this.getDefaultTitle(type),
                message: '',
                autoDismiss: false,
                cooldownSeconds: 5,
                maxRepetitions: 3
            };
        }
        
        // Si config sigue siendo null, usar configuración mínima
        if (!config) {
            console.warn('[ALERT] Config es null, usando configuración mínima');
            config = {
                title: this.getDefaultTitle(type),
                message: '',
                autoDismiss: false,
                cooldownSeconds: 5,
                maxRepetitions: 3
            };
        }
        
        // Verificar reglas de repetición
        const canShow = this.canShowAlert(type, config);
        console.log('[ALERT] canShowAlert resultado:', { type, canShow });
        
        if (!canShow) {
            console.log('[ALERT] Alerta rechazada por reglas de repetición:', type);
            return false;
        }

        // 🔥 VERIFICACIÓN FINAL: Revisar nuevamente si la alerta ya existe
        // (Pudo ser agregada por otra llamada mientras esperábamos getAlertConfig)
        if (this.activeAlerts.has(id)) {
            console.log('[ALERT] ⚠️ Alerta fue agregada por otra llamada durante async, actualizando:', id);
            return this.updateExistingAlert(id, alertData);
        }

        // Mostrar la alerta
        console.log('[ALERT] Mostrando alerta:', { id, type });
        await this.showAlert(alertData, config);

        // Notificar al backend que se mostró
        this.notifyAlertDisplayed(id);
        
        return true;
    }

    // Obtiene la configuración de un tipo de alerta (desde cache o backend)
    async getAlertConfig(type) {
        if (!type) return null;

        if (this.alertConfigs.has(type)) {
            return this.alertConfigs.get(type);
        }

        try {
            const response = await fetch(`/monitoring/api/alerts/config/${type}/`);
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            const data = await response.json();
            
            // Guardar en caché tanto la configuración como los mensajes
            const config = {
                ...data,
                title: data.title || this.getDefaultTitle(type),
                message: data.message || '',
                voice_clip: data.voice_clip || null,
                cooldownSeconds: data.cooldown_seconds || 5,
                maxRepetitions: data.max_repetitions || 3,
                autoDismiss: data.auto_dismiss || false,
                autoDismissDelay: data.auto_dismiss_delay || 5000
            };
            
            this.alertConfigs.set(type, config);
            return config;
        } catch (error) {
            console.error('[ALERT] Error obteniendo configuración:', error);
            return {
                title: this.getDefaultTitle(type),
                message: '',
                cooldownSeconds: 5,
                maxRepetitions: 3,
                autoDismiss: false,
                autoDismissDelay: 5000
            };
        }
    }

    // Verifica si una alerta puede mostrarse según reglas
    canShowAlert(type, config) {
        const now = Date.now();
        const typeState = this.getAlertTypeState(type);

        // Verificar cooldown
        if (typeState.lastShown && (now - typeState.lastShown) < (config.cooldownSeconds * 1000)) {
            const remaining = config.cooldownSeconds * 1000 - (now - typeState.lastShown);
            console.log(`[ALERT] Cooldown activo para ${type}, faltan ${remaining}ms`);
            return false;
        }

        // Verificar límite de repeticiones por hora
        const hourAgo = now - (60 * 60 * 1000);
        const recentShows = typeState.showHistory.filter(time => time > hourAgo).length;
        
        console.log(`[ALERT] Repeticiones recientes para ${type}: ${recentShows}/${config.maxRepetitions}`);
        
        if (recentShows >= config.maxRepetitions) {
            console.log(`[ALERT] Límite de repeticiones alcanzado para ${type}`);
            return false;
        }
        
        return true;
    }

    // Obtiene o inicializa el estado de un tipo de alerta
    getAlertTypeState(type) {
        if (!this._alertStates) {
            this._alertStates = new Map();
        }

        if (!this._alertStates.has(type)) {
            this._alertStates.set(type, {
                showHistory: [],
                lastShown: null,
                repetitionCount: 0
            });
        }

        return this._alertStates.get(type);
    }

    // Muestra una nueva alerta
    async showAlert(alertData, config) {
        const { id, type, metadata = {} } = alertData;
        
        console.log('[ALERT-SHOW] Iniciando showAlert:', { id, type, hasContainer: !!this.container, hasTemplate: !!this.template });
        
        // 🔥 VALIDACIÓN CRÍTICA: Rechazar IDs inválidos
        if (!id || id === 'undefined' || id === null) {
            console.error('[ALERT-SHOW] ❌ ID inválido, rechazando alerta:', { id, type });
            return;
        }
        
        // Verificar que tengamos container y template
        if (!this.container) {
            console.error('[ALERT-SHOW] ❌ Container no encontrado (#alert-container)');
            return;
        }
        
        if (!this.template) {
            console.error('[ALERT-SHOW] ❌ Template no encontrado (#alert-template)');
            return;
        }
        
        // 🔥 CRÍTICO: Verificar si ya existe una alerta con este ID
        if (this.activeAlerts.has(id)) {
            console.log('[ALERT-SHOW] ⚠️ Alerta ya existe en activeAlerts, rechazando duplicado:', id);
            return this.updateExistingAlert(id, alertData);
        }
        
        // 🔥 BLOQUEO INMEDIATO: Marcar ID como "en proceso" para prevenir race conditions
        // Esto previene que dos llamadas simultáneas creen duplicados
        this.activeAlerts.set(id, { 
            element: null,  // Placeholder temporal
            config,
            showTime: Date.now(),
            type,
            inProgress: true  // Marca de construcción
        });
        
        console.log('[ALERT-SHOW] 🔒 ID bloqueado inmediatamente para prevenir duplicados:', id);
        
        // Usar la configuración del backend para títulos y mensajes
        const title = config?.title || alertData.title || this.getDefaultTitle(type);
        const message = config?.message || alertData.message || '';
        const level = metadata.level || config?.level || 'medium';
        
        console.log('[ALERT-SHOW] Título:', title, 'Mensaje:', message);

        // Clonar template
        const alertElement = this.template.content.cloneNode(true);
        const alertCard = alertElement.querySelector('.alert-card');
        
        if (!alertCard) {
            console.error('[ALERT-SHOW] ❌ .alert-card no encontrado en el template');
            return;
        }
        
        alertCard.dataset.alertId = id;
        
        console.log('[ALERT-SHOW] ✓ Template clonado correctamente');
        
        // Configurar estilos según tipo
        this.configureAlertStyles(alertCard, type, level);
        
        // Establecer contenido usando la configuración del backend
        alertCard.querySelector('.alert-title').textContent = title;
        alertCard.querySelector('.alert-message').textContent = message;

        // Configurar ejercicio si existe (DEBE hacerse DESPUÉS de agregar al DOM)
        const hasExercise = metadata.exercise || alertData.exercise;
        console.log('[ALERT-SHOW] ¿Tiene ejercicio?', hasExercise ? 'SÍ' : 'NO', hasExercise);
        
        // 🆕 BREAK REMINDER: Botones especiales "Posponer" y "Descansar"
        if (type === 'break_reminder') {
            console.log('[ALERT] ✨ Configurando botones especiales para break_reminder');
            const actionContainer = alertElement.querySelector('.alert-action');
            actionContainer.innerHTML = ''; // Limpiar botón de ejercicio
            
            // Botón "Posponer" (snooze)
            const snoozeBtn = document.createElement('button');
            snoozeBtn.className = 'exercise-btn';
            snoozeBtn.style.background = '#9CA3AF'; // Gray
            snoozeBtn.style.setProperty('--exercise-hover-bg', '#6B7280');
            snoozeBtn.innerHTML = `
                <i class="fas fa-clock exercise-icon"></i>
                <span class="exercise-text">
                    <span class="exercise-title">Posponer</span>
                    <span class="exercise-duration">5 minutos</span>
                </span>
            `;
            snoozeBtn.onclick = async () => {
                console.log('[BREAK] 🕐 Usuario posponiendo descanso...');
                try {
                    const response = await fetch('/monitoring/api/snooze-break/', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
                        },
                        body: JSON.stringify({ minutes: 5 })
                    });
                    const data = await response.json();
                    if (data.status === 'success') {
                        console.log('[BREAK] ✅ Descanso pospuesto exitosamente');
                        this.closeAlert(id);
                    } else {
                        throw new Error(data.message || 'Error al posponer');
                    }
                } catch (error) {
                    console.error('[BREAK] Error posponiendo:', error);
                    alert('Error al posponer el descanso: ' + error.message);
                }
            };
            
            // Botón "Descansar" (take break)
            const breakBtn = document.createElement('button');
            breakBtn.className = 'exercise-btn';
            breakBtn.style.background = '#6366F1'; // Indigo
            breakBtn.style.setProperty('--exercise-hover-bg', '#4F46E5');
            breakBtn.innerHTML = `
                <i class="fas fa-bed exercise-icon"></i>
                <span class="exercise-text">
                    <span class="exercise-title">Descansar</span>
                    <span class="exercise-duration">Pausar ahora</span>
                </span>
            `;
            breakBtn.onclick = async () => {
                console.log('[BREAK] 😴 Usuario aceptando descanso - pausando monitoreo...');
                try {
                    const response = await fetch('/monitoring/api/break-taken/', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
                        }
                    });
                    const data = await response.json();
                    if (data.status === 'success') {
                        console.log('[BREAK] ✅ Monitoreo pausado para descanso');
                        // Establecer flag de descanso
                        window.isOnBreak = true;
                        // Cerrar la alerta
                        this.closeAlert(id);
                        // Actualizar UI para mostrar contenedor de descanso
                        // (el backend ya pausó la sesión, el polling sincronizará el estado)
                    } else {
                        throw new Error(data.message || 'Error al pausar para descanso');
                    }
                } catch (error) {
                    console.error('[BREAK] Error iniciando descanso:', error);
                    alert('Error al iniciar el descanso: ' + error.message);
                }
            };
            
            // Agregar botones al contenedor
            actionContainer.appendChild(snoozeBtn);
            actionContainer.appendChild(breakBtn);
            actionContainer.style.display = 'flex';
        }

        // Configurar botón de cerrar
        const closeBtn = alertElement.querySelector('.close-alert-btn');
        closeBtn.onclick = () => this.closeAlert(id);

        // Agregar al contenedor
        this.container.appendChild(alertElement);
        
        console.log('[ALERT-SHOW] ✓ Alerta agregada al DOM. Container ahora tiene', this.container.children.length, 'hijos');

        // 🔥 BUSCAR EL alertCard EN EL DOM (después de agregar el fragment, alertCard ya no está en alertElement)
        const addedAlertCard = this.container.querySelector(`[data-alert-id="${id}"]`);
        if (!addedAlertCard) {
            console.error('[ALERT-SHOW] ❌ No se pudo encontrar alertCard en el DOM después de agregar');
            return;
        }
        
        // 🔥 CONFIGURAR EJERCICIO DESPUÉS DE AGREGAR AL DOM
        if (hasExercise) {
            const exerciseData = metadata.exercise || alertData.exercise;
            console.log('[ALERT-SHOW] 🏋️ Configurando botón de ejercicio:', exerciseData);
            this.configureExerciseButton(addedAlertCard, exerciseData, id);
        }

        // 🔥 ACTUALIZAR REFERENCIA: Reemplazar el placeholder con el elemento real
        this.activeAlerts.set(id, { 
            element: addedAlertCard,  // Guardar el elemento real del DOM
            config,
            showTime: Date.now(),
            type,
            inProgress: false  // Ya no está en construcción
        });
        
        console.log('[ALERT-SHOW] ✓ Referencia actualizada con elemento real. Total alertas activas:', this.activeAlerts.size);
        
        // Actualizar propiedades públicas para compatibilidad con el HTML
        this.currentAlertId = id;
        this.currentAlertType = type;

        // Actualizar estado del tipo
        const typeState = this.getAlertTypeState(type);
        typeState.lastShown = Date.now();
        typeState.showHistory.push(Date.now());
        typeState.repetitionCount++;

        // Reproducir audio PRIMERO usando la configuración
        // SOLO UNA VEZ para alertas críticas (driver_absent, multiple_people, camera_occluded)
        const voiceClip = metadata.voice_clip || config?.defaultVoiceClip;
        let audioDuration = 0;
        
        if (voiceClip && this.audioManager) {
            try {
                // Para alertas críticas, solo reproducir una vez
                if (['driver_absent', 'multiple_people', 'camera_occluded'].includes(type)) {
                    // Verificar si ya se reprodujo para este alert_id
                    if (!this._playedAlerts) {
                        this._playedAlerts = new Set();
                    }
                    
                    if (!this._playedAlerts.has(id)) {
                        console.log('[ALERT] 🔊 Reproduciendo audio UNA VEZ para:', type);
                        const result = await this.audioManager.playAlert({
                            id: id,
                            type: type,
                            voice_clip: voiceClip
                        });
                        audioDuration = result?.duration || 0;
                        this._playedAlerts.add(id);
                    } else {
                        console.log('[ALERT] Audio ya reproducido para esta alerta:', id);
                    }
                } else {
                    // Para alertas normales, reproducir siempre
                    console.log('[ALERT] Reproduciendo audio:', voiceClip);
                    const result = await this.audioManager.playAlert({
                        id: id,
                        type: type,
                        voice_clip: voiceClip
                    });
                    audioDuration = result?.duration || 0;
                }
            } catch (error) {
                console.error('[ALERT] Error reproduciendo audio:', error);
            }
        }

        // PAUSA AUTOMÁTICA DESPUÉS DEL AUDIO: Para usuario ausente y múltiples personas
        if (['driver_absent', 'multiple_people'].includes(type)) {
            console.log('[ALERT] ⏸️ Detectada alerta crítica:', type);
            console.log('[ALERT] 🔍 Estado actual - window.isMonitoringActive:', typeof window.isMonitoringActive !== 'undefined' ? window.isMonitoringActive : 'UNDEFINED');
            
            // Esperar a que termine el audio antes de pausar
            if (audioDuration > 0) {
                console.log(`[ALERT] Esperando ${audioDuration.toFixed(0)}ms a que termine el audio antes de pausar...`);
                await new Promise(resolve => setTimeout(resolve, audioDuration + 200)); // +200ms buffer
            }
            
            // 🔥 VERIFICAR: Solo pausar si el monitoreo está activo
            if (typeof window.isMonitoringActive !== 'undefined' && window.isMonitoringActive) {
                console.log('[ALERT] ✅ Pausando monitoreo automáticamente...');
                await this.pauseMonitoringAutomatically(type);
            } else {
                console.log('[ALERT] ⚠️ Monitoreo inactivo o variable undefined, saltando pausa automática');
                console.log('[ALERT] DEBUG: typeof window.isMonitoringActive =', typeof window.isMonitoringActive);
                console.log('[ALERT] DEBUG: window.isMonitoringActive =', typeof window.isMonitoringActive !== 'undefined' ? window.isMonitoringActive : 'UNDEFINED');
            }
        }

        // Auto-cerrar si no tiene ejercicio
        if (!metadata.exercise && config.autoDismiss) {
            setTimeout(() => this.closeAlert(id), config.autoDismissDelay || 5000);
        }
        
        console.log('[ALERT-SHOW] ✓✓✓ Alerta mostrada completamente:', { id, type, title });

        return alertElement;
    }

    // Pausa el monitoreo automáticamente
    async pauseMonitoringAutomatically(alertType) {
        try {
            console.log('[ALERT] Enviando petición de pausa automática para:', alertType);
            
            // Usar la ruta correcta del backend
            const response = await fetch('/monitoring/api/pause/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCsrfToken()
                },
                body: JSON.stringify({
                    reason: `Alerta crítica: ${alertType}`,
                    auto_pause: true
                })
            });
            
            if (response.ok) {
                const data = await response.json();
                console.log('[ALERT] ✓ Monitoreo pausado automáticamente:', data);
                
                // Cerrar/limpiar alertas locales DESPUÉS de que sonó el audio
                try {
                    // Limpiar alertas que estaban esperando delay
                    this.alertsWaitingForDelay.clear();

                    // Cerrar visualmente y limpiar todas las alertas activas
                    console.log('[ALERT] Cerrando alertas tras pausa automática...');
                    if (typeof this.pauseAllAlerts === 'function') {
                        await this.pauseAllAlerts();
                    } else {
                        // Fallback: remover elementos manualmente
                        for (const [aid, info] of this.activeAlerts) {
                            try { info.element?.remove?.(); } catch(_) {}
                        }
                        this.activeAlerts.clear();
                    }

                    // Detener audio Y limpiar reproducciones previas
                    this.audioManager?.clearAllRepeats?.();
                    this.audioManager?.stop?.();

                    // Suprimir temporalmente el tipo para evitar reaparición inmediata
                    try { this.suppressType(alertType, 5000); } catch(_) {}

                    // Limpiar registro de audios reproducidos
                    if (this._playedAlerts) this._playedAlerts.clear();
                } catch (e) {
                    console.warn('[ALERT] Error limpiando alertas tras pausa automática:', e);
                }

                // Actualizar UI del frontend para mostrar estado pausado
                if (window.alertManager && window.alertManager.showPausedState) {
                    window.alertManager.showPausedState(alertType);
                }
                
                // CRÍTICO: Actualizar variables globales y UI del HTML para reflejar pausa
                // Esto asegura que el poller de métricas NO procese nuevas alertas
                // y que la cámara se detenga correctamente
                try {
                    if (typeof window.isPaused !== 'undefined') {
                        window.isPaused = true;
                        console.log('[ALERT] ✓ Variable global isPaused actualizada a true');
                    }
                    
                    // Forzar actualización de UI para detener cámara
                    if (typeof window.setMonitoringState === 'function') {
                        window.setMonitoringState(true, true); // isActive=true, paused=true
                        console.log('[ALERT] ✓ setMonitoringState(true, true) ejecutado - cámara detenida');
                    }
                } catch (e) {
                    console.warn('[ALERT] Error actualizando estado de pausa en HTML:', e);
                }
            } else {
                console.warn('[ALERT] Error al pausar monitoreo:', response.status);
            }
        } catch (error) {
            console.error('[ALERT] Error enviando petición de pausa:', error);
        }
    }

    // Obtiene el token CSRF del DOM
    getCsrfToken() {
        const token = document.querySelector('[name=csrfmiddlewaretoken]');
        if (token) return token.value;
        
        // Alternativa: buscar en cookies
        const name = 'csrftoken=';
        const decodedCookie = decodeURIComponent(document.cookie);
        const cookieArray = decodedCookie.split(';');
        for (let cookie of cookieArray) {
            cookie = cookie.trim();
            if (cookie.indexOf(name) === 0) {
                return cookie.substring(name.length, cookie.length);
            }
        }
        return '';
    }

    // Actualiza una alerta existente
    updateExistingAlert(id, newData) {
        const alertInfo = this.activeAlerts.get(id);
        if (!alertInfo) return;

        const { element, type, config } = alertInfo;
        const { metadata = {} } = newData;

        // Actualizar repetición
        if (metadata.repetition_count !== undefined) {
            const typeState = this.getAlertTypeState(type);
            if (metadata.repetition_count > typeState.repetitionCount) {
                // Nueva repetición
                this.handleAlertRepetition(id, element, config);
            }
        }

        // 🔥 CRÍTICO: Configurar ejercicio si existe (puede venir en newData.exercise o metadata.exercise)
        const exerciseData = newData.exercise || metadata.exercise;
        if (exerciseData) {
            this.configureExerciseButton(element, exerciseData, id);
        }
    }

    // Maneja una repetición de alerta
    handleAlertRepetition(id, element, config) {
        // Efecto visual
        element.classList.add('pulse');
        setTimeout(() => element.classList.remove('pulse'), 2000);

        // Reproducir audio SOLO para alertas que requieren repetición
        // camera_occluded NO debe repetir audio (solo sonar una vez)
        const alertInfo = this.activeAlerts.get(id);
        if (alertInfo) {
            const type = alertInfo.type;
            
            // Solo repetir audio para driver_absent y multiple_people
            if (['driver_absent', 'multiple_people'].includes(type) && alertInfo.config.voice_clip) {
                console.log(`[ALERT] 🔊 Repetición de audio para ${type}`);
                this.audioManager.playAudio(alertInfo.config.voice_clip);
            } else if (type === 'camera_occluded') {
                console.log(`[ALERT] ⏭️ Omitiendo repetición de audio para camera_occluded (solo suena una vez)`);
            } else if (alertInfo.config.voice_clip) {
                this.audioManager.playAudio(alertInfo.config.voice_clip);
            }
            
            // Actualizar estado
            const typeState = this.getAlertTypeState(type);
            typeState.repetitionCount++;
            typeState.lastShown = Date.now();
            typeState.showHistory.push(Date.now());
        }
    }

    // Configura el botón de ejercicio
    configureExerciseButton(alertCard, exercise, alertId) {
        console.log('[ALERT-EXERCISE] 🔍 Iniciando configuración de botón para alerta:', alertId);
        console.log('[ALERT-EXERCISE] 📦 Datos del ejercicio:', exercise);
        console.log('[ALERT-EXERCISE] 🎯 alertCard recibido:', alertCard);
        
        const btn = alertCard.querySelector('.exercise-btn');
        console.log('[ALERT-EXERCISE] 🔎 Botón encontrado:', btn);
        
        if (!btn) {
            console.error('[ALERT-EXERCISE] ❌ No se encontró el botón de ejercicio en la alerta');
            console.error('[ALERT-EXERCISE] 📋 HTML del alertCard:', alertCard.innerHTML);
            return;
        }

        const titleSpan = btn.querySelector('.exercise-title');
        const durationSpan = btn.querySelector('.exercise-duration');
        
        console.log('[ALERT-EXERCISE] 📝 titleSpan:', titleSpan, 'durationSpan:', durationSpan);

        if (!titleSpan || !durationSpan) {
            console.error('[ALERT-EXERCISE] ❌ No se encontraron los spans del botón');
            return;
        }

        titleSpan.textContent = exercise.title;
        if (exercise.duration) {
            durationSpan.textContent = `${exercise.duration} min`;
        }

        // Aplicar color según tipo de ejercicio
        const exerciseColors = {
            'eye_movement': { bg: '#86EFAC', hoverBg: '#65D987', dark: '#4ADE80' },
            'focus': { bg: '#86C6F5', hoverBg: '#60A5FA', dark: '#3B82F6' },
            'relaxation': { bg: '#C084FC', hoverBg: '#A855F7', dark: '#9333EA' },
            'blink': { bg: '#FB923C', hoverBg: '#F97316', dark: '#EA580C' },
            'default': { bg: '#A1A97E', hoverBg: '#8A9268', dark: '#6B7D3E' }
        };

        const color = exerciseColors[exercise.type] || exerciseColors.default;
        btn.style.setProperty('--exercise-bg', color.bg);
        btn.style.setProperty('--exercise-hover-bg', color.hoverBg);

        console.log('[ALERT-EXERCISE] 🎨 Color aplicado:', color);
        console.log('[ALERT-EXERCISE] 👁️ Display ANTES:', btn.style.display);
        
        btn.style.display = 'inline-flex';
        
        console.log('[ALERT-EXERCISE] 👁️ Display DESPUÉS:', btn.style.display);
        console.log('[ALERT-EXERCISE] 📏 Computed display:', window.getComputedStyle(btn).display);
        
        btn.onclick = () => this.handleExerciseClick(alertId, exercise.id);
        
        console.log('[ALERT-EXERCISE] ✓ Botón de ejercicio configurado y visible para alerta:', alertId);
    }

    // Maneja el clic en botón de ejercicio
    async handleExerciseClick(alertId, exerciseId) {
        console.log('[ALERT-EXERCISE] 🏋️ Iniciando ejercicio:', exerciseId, 'para alerta:', alertId);
        
        try {
            // 1. Pausar monitoreo automáticamente
            console.log('[ALERT-EXERCISE] ⏸️ Pausando monitoreo automáticamente...');
            await this.pauseMonitoringForExercise();

            // 2. Cerrar la alerta
            console.log('[ALERT-EXERCISE] 🗑️ Cerrando alerta:', alertId);
            this.closeAlert(alertId);

            // 3. Abrir modal de ejercicio con alertId asociado
            console.log('[ALERT-EXERCISE] 📂 Abriendo modal de ejercicio...');
            if (window.exerciseModalManager) {
                await window.exerciseModalManager.open(exerciseId, {
                    alertId: alertId,
                    onComplete: () => {
                        console.log('[ALERT-EXERCISE] ✅ Ejercicio completado');
                    },
                    onClose: () => {
                        console.log('[ALERT-EXERCISE] Modal cerrado, el usuario puede reanudar');
                    }
                });
            } else {
                console.error('[ALERT-EXERCISE] ❌ exerciseModalManager no disponible');
            }
        } catch (error) {
            console.error('[ALERT-EXERCISE] ❌ Error iniciando ejercicio:', error);
        }
    }

    // Pausa el monitoreo específicamente para realizar un ejercicio
    async pauseMonitoringForExercise() {
        try {
            const response = await fetch('/monitoring/api/pause/', {
                method: 'POST',
                headers: { 
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCsrfToken()
                }
            });

            if (response.ok) {
                console.log('[ALERT-EXERCISE] ✓ Monitoreo pausado para ejercicio');
                
                // Actualizar estado global
                if (typeof window.isMonitoringActive !== 'undefined') {
                    window.isMonitoringActive = true; // Sigue activo pero pausado
                }
                if (typeof window.isPaused !== 'undefined') {
                    window.isPaused = true;
                }
                
                // 🔥 CRÍTICO: Actualizar UI para mostrar estado pausado
                if (typeof window.setMonitoringState === 'function') {
                    window.setMonitoringState(true, true); // isActive=true, paused=true
                    console.log('[ALERT-EXERCISE] ✓ UI actualizada a estado pausado');
                }
            }
        } catch (error) {
            console.error('[ALERT-EXERCISE] Error pausando monitoreo:', error);
        }
    }

    // Cierra una alerta
    async closeAlert(id) {
        const alertInfo = this.activeAlerts.get(id);
        if (!alertInfo) return;

        const { element, type } = alertInfo;

        // Animación de salida
        element.classList.add('closing');
        await new Promise(resolve => setTimeout(resolve, 300));

        // Remover del DOM
        element.remove();
        this.activeAlerts.delete(id);
        
        // Limpiar del registro de audios reproducidos (para que se vuelva a reproducir si aparece de nuevo)
        if (this._playedAlerts) {
            this._playedAlerts.delete(id);
        }
        
        // 🔥 IMPORTANTE: Resetear estado del tipo para permitir nueva detección
        // Especialmente crítico para camera_occluded
        if (type === 'camera_occluded' && this._alertStates) {
            console.log(`[ALERT] 🧹 Limpiando estado de ${type} para permitir nueva detección`);
            this._alertStates.delete(type);
        }
        
        // Limpiar referencias actuales si es esta alerta
        if (this.currentAlertId === id) {
            this.currentAlertId = null;
            this.currentAlertType = null;
        }

        // Notificar al backend
        try {
            await fetch('/api/alerts/acknowledge/', {
                method: 'POST',
                headers: { 
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCsrfToken()
                },
                body: JSON.stringify({ alert_id: id })
            });
        } catch (error) {
            console.error('Error notificando cierre:', error);
        }
    }

    // Alias de closeAlert para compatibilidad con el HTML
    async dismissAlert(alertElement, alertId) {
        try {
            // Si nos pasan un elemento, removerlo directamente
            if (alertElement && alertElement.parentNode) {
                alertElement.classList.add('closing');
                await new Promise(resolve => setTimeout(resolve, 300));
                alertElement.remove();
            }
            
            // Limpiar referencias internas
            this.activeAlerts.delete(alertId);
            
            // Limpiar del registro de audios reproducidos
            if (this._playedAlerts) {
                this._playedAlerts.delete(alertId);
            }
            
            if (this.currentAlertId === alertId) {
                this.currentAlertId = null;
                this.currentAlertType = null;
            }
            
            // Notificar al backend
            try {
                await fetch('/api/alerts/acknowledge/', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ alert_id: alertId })
                });
            } catch (error) {
                console.error('[ALERT] Error notificando cierre:', error);
            }
        } catch (error) {
            console.error('[ALERT] Error en dismissAlert:', error);
        }
    }

    // Suprimir un tipo de alerta temporalmente
    suppressType(type, durationMs = 4000) {
        if (!type) return;
        const until = Date.now() + durationMs;
        this.suppressedTypes.set(String(type), until);
        console.log(`[ALERT] Tipo "${type}" suprimido por ${durationMs}ms`);
    }

    // Verificar si un tipo está suprimido
    isTypeSuppressed(type) {
        if (!type) return false;
        const typeStr = String(type);
        const suppressedUntil = this.suppressedTypes.get(typeStr);
        if (!suppressedUntil) return false;
        
        const now = Date.now();
        if (now >= suppressedUntil) {
            this.suppressedTypes.delete(typeStr);
            return false;
        }
        return true;
    }

    // Notifica al backend que se mostró una alerta
    notifyAlertDisplayed(alertId) {
        if (!alertId) return;
        
        // 🔥 VERIFICAR: Solo notificar si el monitoreo está activo
        if (typeof window.isMonitoringActive !== 'undefined' && !window.isMonitoringActive) {
            console.log('[ALERT] ⚠️ Monitoreo inactivo, saltando notificación de visualización');
            return;
        }

        fetch('/monitoring/api/alerts/notify_played/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCsrfToken()
            },
            body: JSON.stringify({ alert_id: alertId })
        }).catch(error => {
            console.error('[ALERT] Error notificando visualización:', error);
        });
    }

    // Muestra el estado pausado en el contenedor de video
    showPausedState(alertType) {
        try {
            console.log('[ALERT] Mostrando estado pausado del monitoreo');
            
            // Buscar los elementos del DOM relacionados con el video
            const videoContainer = document.getElementById('video-container');
            const videoFeed = document.getElementById('video-feed');
            const placeholder = document.getElementById('placeholder');
            
            if (!videoContainer) {
                console.warn('[ALERT] video-container no encontrado');
                return;
            }
            
            // Crear el contenido de pausa si no existe
            let pausedContent = document.getElementById('paused-content');
            if (!pausedContent) {
                pausedContent = document.createElement('div');
                pausedContent.id = 'paused-content';
                pausedContent.className = 'flex flex-col items-center px-4';
                videoContainer.appendChild(pausedContent);
                console.log('[ALERT] Elemento paused-content creado y agregado al DOM');
            } else {
                console.log('[ALERT] Elemento paused-content ya existe, reutilizando');
            }
            
            // Mapear tipos de alerta a emojis y mensajes
            const pauseMessages = {
                'driver_absent': {
                    emoji: '👤',
                    title: 'Monitoreo Pausado',
                    message: 'Usuario no detectado. El monitoreo se ha pausado automáticamente por seguridad.'
                },
                'multiple_people': {
                    emoji: '👥',
                    title: 'Monitoreo Pausado',
                    message: 'Se detectaron múltiples personas. El monitoreo se ha pausado automáticamente.'
                },
                'exercise': {
                    emoji: '🏋️',
                    title: 'Ejercicio en Progreso',
                    message: 'Realizando ejercicio visual. El monitoreo continuará al terminar.'
                },
                'manual': {
                    emoji: '⏸️',
                    title: 'Monitoreo Pausado',
                    message: 'El monitoreo ha sido pausado. Presiona Reanudar cuando estés listo para continuar.'
                }
            };
            
            const config = pauseMessages[alertType] || {
                emoji: '⏸️',
                title: 'Monitoreo Pausado',
                message: 'El monitoreo se ha pausado.'
            };
            
            // Actualizar contenido
            pausedContent.innerHTML = `
                <div style="font-size: 4rem; margin-bottom: 1rem;">
                    ${config.emoji}
                </div>
                <p style="font-weight: 600; font-size: 0.875rem; margin-bottom: 0.5rem; color: #6B7280;">
                    ${config.title}
                </p>
                <p style="font-size: 0.75rem; line-height: 1.5; color: #9CA3AF; max-width: 280px; text-align: center;">
                    ${config.message}
                </p>
            `;
            
            // Ocultar video y placeholder
            if (videoFeed) videoFeed.style.display = 'none';
            if (placeholder) placeholder.style.display = 'none';
            pausedContent.style.display = 'flex';
            console.log('[ALERT] Estado pausado mostrado con display=flex');
            
        } catch (error) {
            console.error('[ALERT] Error mostrando estado pausado:', error);
        }
    }

    // Configura los estilos de una alerta según su tipo y nivel
    configureAlertStyles(element, type, level) {
        if (!element || !element.style) {
            console.warn('[ALERT] configureAlertStyles: elemento no válido', { element, type, level });
            return;
        }
        
        const styles = this.getAlertStyles(type, level);
        
        if (!styles) {
            console.warn('[ALERT] No se obtuvieron estilos para', type, level);
            return;
        }
        
        try {
            element.style.setProperty('--alert-bg', styles.background);
            element.style.setProperty('--alert-border', styles.border);
            element.style.setProperty('--alert-icon-color', styles.iconColor);
            element.style.setProperty('--alert-title-color', styles.titleColor || '#374151');
            element.style.setProperty('--alert-message-color', styles.messageColor || '#6B7280');
            element.style.setProperty('--exercise-bg', '#A1A97E'); // Verde sage por defecto
        } catch (error) {
            console.error('[ALERT] Error configurando estilos CSS:', error);
        }

        // Actualizar icono si es necesario
        const iconElement = element.querySelector('.alert-icon');
        if (iconElement && styles.icon) {
            try {
                iconElement.className = `alert-icon fas ${styles.icon}`;
            } catch (error) {
                console.error('[ALERT] Error actualizando icono:', error);
            }
        }
    }

    // Obtiene los estilos para un tipo y nivel de alerta
    getAlertStyles(type, level) {
        // Paleta de colores pasteles de Tailwind
        const styles = {
            // Críticas - Rojo suave
            driver_absent: {
                background: '#FEE2E2',  // red-50
                border: '#FCA5A5',      // red-200
                iconColor: '#DC2626',   // red-600
                icon: 'fa-user-slash',
                titleColor: '#991B1B',  // red-900
                messageColor: '#7F1D1D' // red-950
            },
            multiple_people: {
                background: '#FEE2E2',  // red-50
                border: '#FCA5A5',      // red-200
                iconColor: '#DC2626',   // red-600
                icon: 'fa-users',
                titleColor: '#991B1B',
                messageColor: '#7F1D1D'
            },
            // Microsueño - Rosa suave
            microsleep: {
                background: '#FCE7F3',  // pink-50
                border: '#FBCFE8',      // pink-200
                iconColor: '#EC4899',   // pink-500
                icon: 'fa-moon',
                titleColor: '#831843',  // pink-900
                messageColor: '#500724' // pink-950
            },
            // Fatiga - Ámbar suave
            fatigue: {
                background: '#FFFBEB',  // amber-50
                border: '#FED7AA',      // amber-200
                iconColor: '#D97706',   // amber-600
                icon: 'fa-battery-quarter',
                titleColor: '#78350F',  // amber-900
                messageColor: '#451A03' // amber-950
            },
            // Distracción - Azul suave
            distraction: {
                background: '#EFF6FF',  // blue-50
                border: '#BFDBFE',      // blue-200
                iconColor: '#2563EB',   // blue-600
                icon: 'fa-eye-slash',
                titleColor: '#1E3A8A',  // blue-900
                messageColor: '#0C2340' // blue-950
            },
            // Cámara obstruida - Púrpura suave
            camera_occluded: {
                background: '#F3E8FF',  // purple-50
                border: '#E9D5FF',      // purple-200
                iconColor: '#9333EA',   // purple-600
                icon: 'fa-video-slash',
                titleColor: '#4C0519',  // purple-900
                messageColor: '#2E0249' // purple-950
            },
            // Ejercicio - Verde suave
            exercise: {
                background: '#F0FDF4',  // green-50
                border: '#BBFBAE',      // green-200
                iconColor: '#059669',   // green-600
                icon: 'fa-dumbbell',
                titleColor: '#14532D',  // green-900
                messageColor: '#052E16' // green-950
            },
            // Tasa de parpadeo - Cian suave
            low_blink_rate: {
                background: '#ECFDFD',  // cyan-50
                border: '#A5F3FC',      // cyan-200
                iconColor: '#0891B2',   // cyan-600
                icon: 'fa-eye-dropper',
                titleColor: '#164E63',  // cyan-900
                messageColor: '#0C2F39' // cyan-950
            },
            high_blink_rate: {
                background: '#F0FDFA',  // teal-50
                border: '#99F6E4',      // teal-200
                iconColor: '#0D9488',   // teal-600
                icon: 'fa-droplet',
                titleColor: '#134E4A',  // teal-900
                messageColor: '#0D3331' // teal-950
            },
            // Luz baja - Naranja suave
            low_light: {
                background: '#FFEDD5',  // orange-50
                border: '#FDBA74',      // orange-200
                iconColor: '#D97706',   // orange-600
                icon: 'fa-sun',
                titleColor: '#7C2D12',  // orange-900
                messageColor: '#431407' // orange-950
            },
            // Foco - Indigo suave
            focus_lost: {
                background: '#EEF2FF',  // indigo-50
                border: '#C7D2FE',      // indigo-200
                iconColor: '#4F46E5',   // indigo-600
                icon: 'fa-target',
                titleColor: '#312E81',  // indigo-900
                messageColor: '#1E1B4B' // indigo-950
            },
            // Defecto - Gris suave
            default: {
                background: '#F9FAFB',  // gray-50
                border: '#D1D5DB',      // gray-300
                iconColor: '#6B7280',   // gray-500
                icon: 'fa-bell',
                titleColor: '#374151',  // gray-700
                messageColor: '#6B7280' // gray-500
            }
        };

        // Ajustar según nivel
        let baseStyles = styles[type] || styles.default;
        if (level === 'high' || level === 'critical') {
            baseStyles = {
                ...baseStyles,
                background: '#FEE2E2',  // red-50
                border: '#FECACA',      // red-300
                iconColor: '#DC2626'    // red-600
            };
        }

        return baseStyles;
    }

    // Actualiza los estilos de todas las alertas activas (ej: cambio modo oscuro)
    updateAllAlertStyles() {
        for (const [id, alertInfo] of this.activeAlerts) {
            const { element, type } = alertInfo;
            this.configureAlertStyles(element, type);
        }
    }

    // Obtiene el título por defecto según el tipo
    getDefaultTitle(type) {
        const titles = {
            microsleep: 'Microsueño Detectado',
            fatigue: 'Fatiga Visual',
            distraction: 'Distracción Detectada',
            low_blink_rate: 'Tasa de Parpadeo Baja',
            high_blink_rate: 'Tasa de Parpadeo Alta',
            low_light: 'Iluminación Baja',
            default: 'Alerta'
        };
        return titles[type] || titles.default;
    }

    // Limpia todas las alertas activas
    async clear() {
        try {
            console.log('[ALERT] 🧹 Iniciando limpieza completa de alertas...');
            
            // 🔥 CRÍTICO: Cerrar la conexión SSE PRIMERO y marcar como null
            if (this.evtSource) {
                console.log('[ALERT] 🔌 Cerrando EventSource...');
                this.evtSource.close();
                this.evtSource = null;  // Marcar como null para evitar reconexión
                console.log('[ALERT] ✅ EventSource cerrado exitosamente');
            }

            // Limpiar alertas que estaban esperando delay
            if (this.alertsWaitingForDelay.size > 0) {
                console.log(`[ALERT] 🧹 Limpiando ${this.alertsWaitingForDelay.size} alertas en espera de delay`);
                this.alertsWaitingForDelay.clear();
            }

            // Obtener todos los IDs de alertas activas
            const activeAlertIds = Array.from(this.activeAlerts.keys());
            
            if (activeAlertIds.length > 0) {
                console.log(`[ALERT] 🧹 Limpiando ${activeAlertIds.length} alertas activas`);
            }

            // Notificar al backend que todas las alertas se están cerrando
            try {
                await fetch('/monitoring/api/alerts/cleanup/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this.getCsrfToken()
                    }
                });
                console.log('[ALERT] ✅ Backend notificado de limpieza');
            } catch (error) {
                console.warn('[ALERT] ⚠️ Error notificando limpieza de alertas:', error);
            }

            // Cerrar todas las alertas visualmente
            for (const alertId of activeAlertIds) {
                const alertInfo = this.activeAlerts.get(alertId);
                if (alertInfo && alertInfo.element) {
                    alertInfo.element.classList.add('closing');
                }
            }

            // Esperar a que termine la animación
            await new Promise(resolve => setTimeout(resolve, 300));

            // Remover todos los elementos
            for (const [id, alertInfo] of this.activeAlerts) {
                if (alertInfo.element && alertInfo.element.parentNode) {
                    alertInfo.element.remove();
                }
            }

            // Limpiar colecciones
            this.activeAlerts.clear();
            this._alertStates?.clear();
            this.alertConfigs.clear();

            console.log('[AlertManager] Todas las alertas han sido limpiadas');
        } catch (error) {
            console.error('Error limpiando alertas:', error);
        }
    }

    // Pausa todas las alertas visibles (se cierra al pausar o detener sesión)
    async pauseAllAlerts() {
        try {
            console.log('[ALERT] Cerrando todas las alertas visibles...');
            
            // Obtener todos los IDs de alertas activas
            const activeAlertIds = Array.from(this.activeAlerts.keys());

            // Agregar clase de cierre a todas las alertas
            for (const alertId of activeAlertIds) {
                const alertInfo = this.activeAlerts.get(alertId);
                if (alertInfo && alertInfo.element) {
                    alertInfo.element.classList.add('closing');
                }
            }

            // Esperar a que termine la animación
            await new Promise(resolve => setTimeout(resolve, 300));

            // Remover todos los elementos
            for (const [id, alertInfo] of this.activeAlerts) {
                if (alertInfo.element && alertInfo.element.parentNode) {
                    alertInfo.element.remove();
                }
            }

            // Limpiar colecciones
            this.activeAlerts.clear();
            this.currentAlertId = null;
            this.currentAlertType = null;

            // Limpiar audios reproducidos para permitir que se vuelvan a reproducir si reaparece
            if (this._playedAlerts) {
                this._playedAlerts.clear();
            }

            console.log('[ALERT] ✓ Todas las alertas han sido cerradas');
        } catch (error) {
            console.error('[ALERT] Error cerrando alertas:', error);
        }
    }

    // Manejar la lógica al reanudar: limpiar colas, timers y estados para empezar desde cero
    async handleResume() {
        try {
            console.log('[ALERT] Manejo de reanudar: limpiando estados de AlertManager...');

            // Limpiar alertas en espera de delay
            try { this.alertsWaitingForDelay.clear(); } catch(_) {}

            // Detener audio y limpiar repeticiones
            try { this.audioManager?.clearAllRepeats?.(); } catch(_) {}
            try { this.audioManager?.stop?.(); } catch(_) {}

            // Limpiar alertas visibles
            try {
                for (const [id, alertInfo] of this.activeAlerts) {
                    try { if (alertInfo.element && alertInfo.element.parentNode) alertInfo.element.remove(); } catch(_) {}
                }
                this.activeAlerts.clear();
            } catch (_) {}

            // Limpiar estados por tipo
            try { this._alertStates?.clear?.(); } catch(_) {}

            // Limpiar registro de audios reproducidos
            if (this._playedAlerts) this._playedAlerts.clear();

            // Resetear variables globales de histéresis que pudiera usar el script de métricas
            try {
                const histVars = [
                    '_driverAbsentStart','_driverAbsentAlert','_driverAbsentResolveStart',
                    '_multiplePeopleStart','_multiplePeopleAlert','_multiplePeopleResolveStart',
                    '_cameraOccludedStart','_cameraOccludedAlert','_cameraOccludedResolveStart'
                ];
                histVars.forEach(v => { try { window[v] = null; } catch(_) {} });
            } catch (_) {}

            console.log('[ALERT] Estados de AlertManager reiniciados tras reanudar');
        } catch (error) {
            console.error('[ALERT] Error en handleResume:', error);
        }
    }

    // Obtiene el token CSRF
    getCsrfToken() {
        return document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
    }
}

// Agregar al objeto window
window.AlertNotificationManager = AlertNotificationManager;

} // Fin del bloque if

// Inicializar cuando el DOM esté listo
document.addEventListener('DOMContentLoaded', async () => {
    try {
        // Inicializar AudioManager primero con configuración del usuario
        if (!window.alertAudioManager) {
            console.log('[INIT] Inicializando sistema de audio...');
            // Usar configuración global del usuario si está disponible
            const audioConfig = window.userConfig || {
                alert_volume: 0.7,
                notification_sound_enabled: true
            };
            window.alertAudioManager = new AlertAudioManager(audioConfig);
            await window.alertAudioManager.initialize();
        }

        // Luego inicializar AlertManager
        if (!window.alertManager) {
            console.log('[INIT] Inicializando sistema de alertas...');
            window.alertManager = new AlertNotificationManager();
        }
        
        // Configurar interacción para audio
        const handleInteraction = () => {
            document.documentElement.dataset.userInteracted = 'true';
            if (window.alertAudioManager?.audioContext?.state === 'suspended') {
                window.alertAudioManager.audioContext.resume();
            }
        };
        
        ['click', 'touchstart'].forEach(event => {
            document.addEventListener(event, handleInteraction, { once: true });
        });

        console.log('[INIT] Sistemas de notificación inicializados correctamente');
    } catch (error) {
        console.error('[INIT] Error durante la inicialización:', error);
    }
});

})(); // Fin del IIFE