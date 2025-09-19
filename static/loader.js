// Loader Futurista Médico PRO
// Loader Premium: opción para desactivar desde config
window.SHOW_MEDICAL_LOADER = (typeof window.SHOW_MEDICAL_LOADER !== 'undefined') ? window.SHOW_MEDICAL_LOADER : true;
console.log('[Loader] loader.js cargado');

// === ADN PARTICLES ===
function createDnaParticles() {
    const dnaContainer = document.querySelector('.dna-particles');
    if (!dnaContainer) return;
    dnaContainer.innerHTML = '';
    const helixCount = 3;
    const helixColors = [
        'linear-gradient(135deg, #22d3ee 0%, #6366f1 100%)',
        'linear-gradient(135deg, #06b6d4 0%, #a21caf 100%)',
        'linear-gradient(135deg, #0ea5e9 0%, #a7f3d0 100%)'
    ];
    for (let h = 0; h < helixCount; h++) {
        const helix = document.createElement('div');
        helix.className = 'dna-helix';
        helix.style.setProperty('--helix-index', h);
        helix.style.background = helixColors[h % helixColors.length];
        helix.style.filter = 'drop-shadow(0 0 24px #a21caf88) drop-shadow(0 0 32px #22d3ee88)';
        for (let i = 0; i < 22; i++) {
            const base = document.createElement('div');
            base.className = 'dna-base';
            base.style.setProperty('--i', i);
            base.style.boxShadow =
                '0 0 18px #a21cafcc, 0 0 8px #22d3eecc, 0 0 2px #fff';
            base.style.background =
                i % 2 === 0
                    ? 'linear-gradient(135deg, #a21caf 0%, #22d3ee 100%)'
                    : 'linear-gradient(135deg, #06b6d4 0%, #6366f1 100%)';
            helix.appendChild(base);
        }
        dnaContainer.appendChild(helix);
    }
    // Efecto extra: partículas glow flotantes
    for (let i = 0; i < 14; i++) {
        const glow = document.createElement('div');
        glow.className = 'dna-glow-particle';
        glow.style.left = Math.random() * 100 + '%';
        glow.style.top = Math.random() * 100 + '%';
        glow.style.animationDelay = (Math.random() * 4) + 's';
        glow.style.background =
            'radial-gradient(circle, #a21caf88 0%, #22d3eecc 60%, transparent 100%)';
        dnaContainer.appendChild(glow);
    }
}

// === PARTICULAS FLOTANTES PREMIUM ===
function createParticles() {
    const particlesContainer = document.querySelector('.particles');
    if (!particlesContainer) return;
    particlesContainer.innerHTML = '';
    const particleCount = 60;
    const colors = [
        'linear-gradient(135deg, #22d3ee 0%, #6366f1 50%, #a855f7 100%)',
        'linear-gradient(135deg, #06b6d4, #8b5cf6)',
        'linear-gradient(135deg, #0ea5e9, #ec4899)',
        'linear-gradient(135deg, #a21caf, #22d3ee)'
    ];
    for (let i = 0; i < particleCount; i++) {
        const particle = document.createElement('div');
        particle.classList.add('particle');
        particle.style.left = Math.random() * 100 + '%';
        particle.style.animationDelay = (Math.random() * 12) + 's';
        particle.style.animationDuration = (7 + Math.random() * 10) + 's';
        particle.style.background = colors[i % colors.length];
        const size = 5 + Math.random() * 12;
        particle.style.width = size + 'px';
        particle.style.height = size + 'px';
        particle.style.boxShadow =
            '0 0 24px #a21cafcc, 0 0 32px #22d3eecc, 0 0 8px #fff8';
        particlesContainer.appendChild(particle);
    }
}

window.addEventListener('DOMContentLoaded', function() {
    if (!window.SHOW_MEDICAL_LOADER) {
        const loader = document.getElementById('medicalLoading');
        if (loader) loader.style.display = 'none';
        document.body.classList.remove('loading');
        return;
    }
    const loader = document.getElementById('medicalLoading');
    const progressFill = document.getElementById('progressFill');
    const progressPercent = document.getElementById('progressPercent');
    const subtitle = document.getElementById('loadingSubtitle');
    const statusDb = document.getElementById('status-db');      // Forzar estilo del título para eliminar borrosidad
    const loaderTitle = document.getElementById('loaderTitle');
    // Eliminar cualquier forzado de estilos visuales desde JS, dejar solo el texto
    if (loaderTitle) {
        loaderTitle.textContent = 'SISTEMA MÉDICO';
        // Debug opcional
        // console.log('Loader title element found:', loaderTitle);
    } else {
        console.error('Loader title element not found!');
    }
    
    // El loader espera un status-server, pero no existe en loader.html, así que lo creamos virtualmente para la animación
    let statusServer = document.getElementById('status-server');
    if (!statusServer) {
        // Crear un div temporal invisible para no romper la animación
        statusServer = document.createElement('div');
        statusServer.style.display = 'none';
        document.body.appendChild(statusServer);
    }
    const statusSec = document.getElementById('status-sec');
    const messages = [
        'Inicializando protocolo avanzado...',
        'Verificando base de datos...',
        'Conectando con el servidor...',
        'Activando sistemas de seguridad...',
        '¡Listo para usar!'
    ];
    let percent = 0;
    let msgIndex = 0;
    let duration = 4200; // 4.2 segundos: premium, rápido pero visible
    let intervalMs = 18; // ultra fluido
    let steps = Math.floor(duration / intervalMs); // Usar Math.floor para asegurar el 100%
    let step = 0;
    let loaderReady = false;
    let pageLoaded = false;
    let interval = null;
    function finishLoader() {
        console.log('[Loader] ¿loaderReady?', loaderReady, '| ¿pageLoaded?', pageLoaded);
        if (loaderReady && pageLoaded) {
            // Completa la barra y oculta el loader
            if (progressFill) {
                progressFill.style.width = '100%';
                progressFill.style.transition = 'width 0.7s cubic-bezier(.4,2,.6,1)';
            }
            if (progressPercent) progressPercent.textContent = '100%';
            subtitle.textContent = messages[4];
            setTimeout(() => {
                if (loader) {
                    loader.classList.add('hidden');
                    loader.style.transition = 'opacity 0.6s cubic-bezier(.4,2,.6,1)';
                    loader.style.opacity = '0';
                    document.body.classList.remove('loading');
                    setTimeout(() => {
                        if (loader.parentNode) loader.parentNode.removeChild(loader);
                        console.log('[Loader] Loader oculto y eliminado.');
                    }, 700);
                }
            }, 500);
        }
    }
    function animateLoader() {
        interval = setInterval(() => {
            step++;
            // Solo avanza hasta 90% hasta que la página esté lista
            let maxPercent = pageLoaded ? 100 : 90;
            let currentTarget = Math.min(Math.round((step / steps) * 100), maxPercent);
            percent = currentTarget;
            if (progressFill) {
                progressFill.style.width = percent + '%';
                progressFill.style.transition = 'width 0.7s cubic-bezier(.4,2,.6,1)';
            }
            if (progressPercent) progressPercent.textContent = percent + '%';
            if (step % 10 === 0) console.log('[Loader] Progreso:', percent + '%');
            if (percent >= 18 && msgIndex === 0) {
                subtitle.textContent = messages[1];
                setStatusChecked(statusDb, 'Base de Datos');
                msgIndex = 1;
                console.log('[Loader] Estado: Base de Datos');
            }
            if (percent >= 48 && msgIndex === 1) {
                subtitle.textContent = messages[2];
                setStatusChecked(statusServer, 'Servidor');
                msgIndex = 2;
                console.log('[Loader] Estado: Servidor');
            }
            if (percent >= 78 && msgIndex === 2) {
                subtitle.textContent = messages[3];
                setStatusChecked(statusSec, 'Seguridad');
                msgIndex = 3;
                console.log('[Loader] Estado: Seguridad');
            }
            // NUEVO: marcar el último status (Monitoreo) antes de finalizar
            if (percent >= 90 && msgIndex === 3) {
                const statusHeart = document.getElementById('status-heart');
                setStatusChecked(statusHeart, 'Monitoreo');
                msgIndex = 4;
                console.log('[Loader] Estado: Monitoreo');
                // NUEVO: Esperar 200ms antes de permitir finalizar el loader
                setTimeout(() => {
                    loaderReady = true;
                }, 200);
            }
            if (percent >= maxPercent && msgIndex >= 4) {
                clearInterval(interval);
                console.log('[Loader] Loader listo para finalizar.');
                finishLoader();
            }
        }, intervalMs);
    }
    // Asegura que la función esté definida antes de usarla
    function setStatusChecked(el, label) {
        if (el) {
            el.classList.add('checked');
            if (label) console.log('✅ Estado activado:', label);
        }
    }
    // Forzar el loader a ejecutarse siempre, incluso si la página se recarga rápido
    if (loader) {
        loader.classList.remove('hidden');
        loader.style.opacity = '1';
        loader.style.transition = '';
        // Reiniciar barra y porcentaje SIEMPRE antes de animar
        if (progressFill) {
            progressFill.style.transition = 'none';
            progressFill.style.width = '0%';
            // Forzar reflow para reiniciar transición visual
            void progressFill.offsetWidth;
            progressFill.style.transition = 'width 0.7s cubic-bezier(.4,2,.6,1)';
        }
        if (progressPercent) progressPercent.textContent = '0%';
        if (statusDb) statusDb.classList.remove('checked');
        if (statusServer) statusServer.classList.remove('checked');
        if (statusSec) statusSec.classList.remove('checked');
        subtitle.textContent = messages[0];
        // Esperar a que todo el DOM esté listo y forzar el loader
        setTimeout(() => {
            // Solo animar si el loader sigue visible
            if (loader && loader.style.opacity !== '0') {
                animateLoader();
            }
        }, 350);
        // Evitar que el loader se oculte por otros scripts antes de tiempo
        window.addEventListener('beforeunload', function(e) {
            if (loader) loader.classList.remove('hidden');
        });
    }

    // Función que se ejecuta cuando el loader termina
    function onLoaderComplete() {
        // Remover clase loading del body
        document.body.classList.remove('loading');
        
        // Activar el tema oscuro del dashboard
        setTimeout(() => {
            if (window.forceHealthFlowTheme) {
                window.forceHealthFlowTheme();
            }
        }, 500);
        
        console.log('🎯 Loader completed, activating dark theme');
    }

    // Agregar clase loading al body inicialmente
    document.body.classList.add('loading');

    // Forzar finalización si algo falla (timeout de seguridad)
    setTimeout(() => {
        if (!loaderReady || !pageLoaded) {
            console.warn('[Loader] Timeout de seguridad: forzando cierre del loader.');
            loaderReady = true;
            pageLoaded = true;
            finishLoader();
        }
    }, 8000); // 8 segundos máximo

    createParticles();
    createDnaParticles();
});

window.addEventListener('load', function() {
    pageLoaded = true;
    console.log('[Loader] Evento window.onload recibido.');
    finishLoader();
    // Solo forzar ocultar y eliminar el loader si sigue visible después de 7 segundos (por error)
    const loader = document.getElementById('medicalLoading');
    setTimeout(() => {
        if (loader && !loader.classList.contains('hidden')) {
            loader.classList.add('hidden');
            loader.style.transition = 'opacity 0.6s cubic-bezier(.4,2,.6,1)';
            loader.style.opacity = '0';
            document.body.classList.remove('loading');
            setTimeout(() => {
                if (loader.parentNode) loader.parentNode.removeChild(loader);
            }, 700);
        }
    }, 7000); // Solo si el loader sigue tras 7s
});
