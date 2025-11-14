import json
import logging
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.exercises.models import ExerciseSession
from apps.monitoring.models import (
    AlertEvent,
    AlertExerciseMapping,
    AlertTypeConfig,
    MonitorSession,
)
from .controller import controller

logger = logging.getLogger(__name__)

@login_required
@require_http_methods(["GET"])
def get_next_alert(request):
    try:
        active_session = MonitorSession.objects.filter(
            user=request.user,
            end_time__isnull=True
        ).order_by('-start_time').first()
        
        if not active_session:
            return JsonResponse({'status': 'success', 'alert': None})

        # 🔧 CORRECCIÓN 1: Verificar pausa PRIMERO
        session_paused = False
        try:
            if hasattr(controller, 'camera_manager') and controller.camera_manager:
                session_paused = bool(controller.camera_manager.is_paused)
        except Exception as e:
            logger.error(f"[ALERT] Error verificando pausa: {e}")

        if session_paused:
            logger.info(f"[ALERT] ⛔ Sesión pausada, no devolviendo alertas")
            return JsonResponse({
                'status': 'success', 
                'alert': None, 
                'session_paused': True
            })

        now = timezone.now()
        
        # Auto-limpiar alertas antiguas (excepto críticas)
        old_alerts = AlertEvent.objects.filter(
            session=active_session,
            resolved_at__isnull=True,
            triggered_at__lt=now - timezone.timedelta(seconds=10)
        ).exclude(
            alert_type__in=[
                AlertEvent.ALERT_DRIVER_ABSENT,
                AlertEvent.ALERT_MULTIPLE_PEOPLE,
                AlertEvent.ALERT_CAMERA_OCCLUDED
            ]
        )
        
        for alert in old_alerts:
            alert.mark_resolved(method='auto_cleanup')

        # 🔧 CORRECCIÓN 2: Obtener SOLO UNA alerta pendiente
        pending_alerts = AlertEvent.objects.filter(
            session=active_session,
            resolved_at__isnull=True
        ).filter(
            Q(exercise_session__isnull=True) |
            Q(exercise_session__completed=True)
        ).select_related('session', 'exercise_session').order_by('triggered_at')

        # 🔧 CORRECCIÓN 3: Filtrar alertas en cooldown
        alert_obj = None
        for candidate in pending_alerts:
            # Si nunca se ha reproducido, es candidata
            if candidate.repeat_count == 0:
                alert_obj = candidate
                logger.info(f"[ALERT] 🆕 Primera vez: {candidate.id} ({candidate.alert_type})")
                break
            
            # Si ya se reprodujo, verificar cooldown
            if candidate.last_repeated_at:
                elapsed = (now - candidate.last_repeated_at).total_seconds()
                
                # Obtener intervalo configurado (per-user)
                repeat_interval = 10
                try:
                    user_cfg = getattr(request.user, 'monitoring_config', None)
                    if user_cfg and getattr(user_cfg, 'alert_repeat_interval', None) is not None:
                        repeat_interval = int(user_cfg.alert_repeat_interval)
                except Exception:
                    pass
                
                # Verificar si pasó el cooldown
                if elapsed >= repeat_interval:
                    alert_obj = candidate
                    logger.info(f"[ALERT] 🔄 Cooldown cumplido: {candidate.id} ({elapsed:.1f}s >= {repeat_interval}s)")
                    break
                else:
                    logger.debug(f"[ALERT] ⏰ En cooldown: {candidate.id} ({elapsed:.1f}s < {repeat_interval}s)")

        if not alert_obj:
            return JsonResponse({'status': 'success', 'alert': None})

        # Preparar respuesta
        try:
            # Obtener configuración
            priority = 5
            try:
                mapping = AlertExerciseMapping.objects.get(
                    alert_type=alert_obj.alert_type, 
                    is_active=True
                )
                priority = mapping.priority or 5
            except AlertExerciseMapping.DoesNotExist:
                pass

            # Ejercicio asociado
            exercise_data = None
            try:
                mapping = AlertExerciseMapping.objects.get(
                    alert_type=alert_obj.alert_type, 
                    is_active=True
                )
                if mapping.exercise:
                    duration_minutes = getattr(mapping.exercise, 'total_duration_minutes', None)
                    if callable(duration_minutes):
                        duration_minutes = duration_minutes()
                    exercise_data = {
                        'id': mapping.exercise.id,
                        'title': mapping.exercise.title,
                        'description': mapping.exercise.description,
                        'duration': duration_minutes or 0
                    }
            except AlertExerciseMapping.DoesNotExist:
                pass

            # Voice clip
            vc = None
            if getattr(alert_obj, 'voice_clip', None):
                try:
                    vc = alert_obj.voice_clip.url
                except Exception:
                    pass
            
            if not vc:
                try:
                    type_config = AlertTypeConfig.objects.get(alert_type=alert_obj.alert_type)
                    if type_config.default_voice_clip:
                        vc = type_config.default_voice_clip.url
                except Exception:
                    pass

            # Descripción
            alert_description = None
            try:
                tc = AlertTypeConfig.objects.get(alert_type=alert_obj.alert_type)
                alert_description = tc.description or None
            except Exception:
                pass

            # Configuración de histéresis y repeticiones
            # Obtener configuración del usuario
            try:
                user_cfg = getattr(request.user, 'monitoring_config', None)
                configured_max_reps = int(getattr(user_cfg, 'repeat_max_per_hour', 12) or 12)
                configured_repeat_interval = int(getattr(user_cfg, 'alert_repeat_interval', 5) or 5)
            except Exception:
                configured_max_reps = 12
                configured_repeat_interval = 5
            
            # Para alertas críticas, usar la configuración del usuario
            HYST_TYPES = {
                AlertEvent.ALERT_CAMERA_OCCLUDED: {
                    'max_reps': configured_max_reps,  # Usar config de usuario
                    'repeat_interval': configured_repeat_interval
                },
                AlertEvent.ALERT_DRIVER_ABSENT: {
                    'max_reps': configured_max_reps,  # Usar config de usuario
                    'repeat_interval': configured_repeat_interval
                },
                AlertEvent.ALERT_MULTIPLE_PEOPLE: {
                    'max_reps': configured_max_reps,  # Usar config de usuario
                    'repeat_interval': configured_repeat_interval
                },
            }

            has_exercise = bool(exercise_data)
            is_hysteresis_alert = alert_obj.alert_type in HYST_TYPES
            
            # Determinar máximo de repeticiones según el tipo
            if is_hysteresis_alert:
                hyst_cfg = HYST_TYPES.get(alert_obj.alert_type)
                max_reps = hyst_cfg['max_reps']
                repeat_interval = hyst_cfg['repeat_interval']
            elif has_exercise:
                max_reps = configured_max_reps  # Usar configuración para alertas con ejercicios
                repeat_interval = configured_repeat_interval
            else:
                max_reps = 1  # Alertas simples se muestran solo una vez
                repeat_interval = configured_repeat_interval

            rep_count = alert_obj.repeat_count
            last_rep = alert_obj.last_repeated_at
            
            # 🔧 CORRECCIÓN 4: Lógica de reproducción clara
            play_audio = False
            next_due_in = 0
            
            # Primera vez
            if rep_count == 0:
                play_audio = True
                next_due_in = 0
            else:
                # Verificar límite de repeticiones
                if max_reps is not None and rep_count >= max_reps:
                    if has_exercise:
                        # Para alertas con ejercicio: no mostrar más pero mantener el cooldown normal
                        play_audio = False
                        if last_rep:
                            elapsed = (now - last_rep).total_seconds()
                            next_due_in = max(0, repeat_interval - elapsed)
                        else:
                            next_due_in = repeat_interval
                    else:
                        # Para alertas sin ejercicio: no mostrar nunca más
                        play_audio = False
                        next_due_in = 999999  # Nunca más
                else:
                    # Verificar cooldown
                    if last_rep:
                        elapsed = (now - last_rep).total_seconds()
                        next_due_in = max(0, repeat_interval - elapsed)
                        play_audio = (next_due_in == 0)
                    else:
                        play_audio = True
                        next_due_in = 0

            logger.info(f"[ALERT] 📤 Devolviendo: {alert_obj.id} (rep={rep_count}, play={play_audio}, next={next_due_in:.1f}s)")

            return JsonResponse({
                'status': 'success',
                'alert': {
                    'id': alert_obj.id,
                    'type': alert_obj.alert_type,
                    'level': alert_obj.level,
                    'message': alert_obj.message,
                    'description': alert_description,
                    'priority': priority,
                    'triggered_at': alert_obj.triggered_at.isoformat(),
                    'voice_clip': vc,
                    'metadata': alert_obj.metadata or {},
                    'exercise': exercise_data,
                    'repeat_count': rep_count,
                    'last_repeated_at': last_rep.isoformat() if last_rep else None,
                    'repeat_interval_seconds': repeat_interval,
                    'next_due_in_seconds': next_due_in,
                    'play_audio': play_audio,
                    'is_exercise_alert': has_exercise,
                    'is_hysteresis_alert': is_hysteresis_alert,
                    'max_repetitions': max_reps,
                    'session_paused': False
                }
            })

        except Exception as e:
            logger.error(f"[ALERT] Error procesando {alert_obj.id}: {e}", exc_info=True)
            return JsonResponse({'status': 'success', 'alert': None})

    except Exception as e:
        logger.error(f"[ALERT] Error: {e}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def notify_alert_audio_played(request):
    """
    🔧 VERSIÓN CORREGIDA: Actualizar y pausar si es necesario
    """
    try:
        data = json.loads(request.body)
        alert_id = data.get('alert_id')
        
        if not alert_id:
            return JsonResponse({
                'status': 'error', 
                'message': 'alert_id requerido'
            }, status=400)

        now = timezone.now()
        session_paused = False

        with transaction.atomic():
            try:
                alert_obj = AlertEvent.objects.select_for_update().get(
                    id=alert_id,
                    session__user=request.user,
                    resolved_at__isnull=True
                )
            except AlertEvent.DoesNotExist:
                logger.warning(f"[ALERT-NOTIFY] Alerta {alert_id} no encontrada o ya resuelta")
                return JsonResponse({
                    'status': 'error', 
                    'message': 'Alerta no encontrada'
                }, status=404)

            # Configuración por usuario (sin depender de AlertTypeConfig para tiempos)
            try:
                user_cfg = getattr(request.user, 'monitoring_config', None)
                hysteresis_timeout = float(getattr(user_cfg, 'hysteresis_timeout_seconds', 30.0) or 30.0)
                configured_max_reps = int(getattr(user_cfg, 'repeat_max_per_hour', 12) or 12)
            except Exception:
                configured_max_reps = 12
                hysteresis_timeout = 30.0
            
            # Definir tipos con histéresis y sus configuraciones
            HYST_TYPES = {
                AlertEvent.ALERT_CAMERA_OCCLUDED: {
                    'max_reps': configured_max_reps,  # Usar config de usuario
                    'timeout': hysteresis_timeout
                },
                AlertEvent.ALERT_DRIVER_ABSENT: {
                    'max_reps': configured_max_reps,  # Usar config de usuario
                    'timeout': hysteresis_timeout
                },
                AlertEvent.ALERT_MULTIPLE_PEOPLE: {
                    'max_reps': configured_max_reps,  # Usar config de usuario
                    'timeout': hysteresis_timeout
                },
            }

            has_exercise = False
            try:
                mapping = AlertExerciseMapping.objects.get(
                    alert_type=alert_obj.alert_type, 
                    is_active=True
                )
                has_exercise = bool(mapping.exercise)
            except AlertExerciseMapping.DoesNotExist:
                pass

            hyst_cfg = HYST_TYPES.get(alert_obj.alert_type)
            max_reps = hyst_cfg['max_reps'] if hyst_cfg else (configured_max_reps if has_exercise else 1)
            is_hysteresis = alert_obj.alert_type in HYST_TYPES

            # Incrementar contador
            alert_obj.repeat_count += 1
            alert_obj.last_repeated_at = now
            alert_obj.save(update_fields=['repeat_count', 'last_repeated_at'])

            new_rep_count = alert_obj.repeat_count
            logger.info(f"[ALERT-NOTIFY] ✅ {alert_id} reproducida. Rep: {new_rep_count}/{max_reps or '∞'}")

            # 🔧 CORRECCIÓN: Verificar si debe pausar
            # NOTA: Para alertas críticas, max_reps=None, así que la pausa se maneja
            # en controller.py basándose en detection_time > hysteresis_timeout
            is_auto_pause_type = alert_obj.alert_type in [
                AlertEvent.ALERT_DRIVER_ABSENT,
                AlertEvent.ALERT_MULTIPLE_PEOPLE
            ]

            if is_auto_pause_type and max_reps is not None and new_rep_count >= max_reps:
                logger.warning(f"[ALERT-NOTIFY] 🚨 Límite alcanzado ({new_rep_count}/{max_reps}), pausando sesión")
                
                # Pausar sesión
                try:
                    ok, msg, _ = controller.pause_session()
                    session_paused = bool(ok)
                    logger.info(f"[ALERT-NOTIFY] Pausa: {msg} (ok={ok})")
                except Exception as pause_err:
                    logger.error(f"[ALERT-NOTIFY] Error pausando: {pause_err}", exc_info=True)
                    session_paused = False

                # Resolver alerta
                meta = alert_obj.metadata or {}
                meta.update({
                    'auto_paused_after_repetitions': True,
                    'repetition_limit_reached': True,
                    'repetition_count': int(new_rep_count),
                    'resolved_by_auto_pause': True,
                    'resolution_time': now.isoformat(),
                })
                alert_obj.resolution_method = 'auto_pause'
                alert_obj.metadata = meta
                alert_obj.mark_resolved()
                alert_obj.save(update_fields=['resolution_method', 'metadata', 'resolved', 'resolved_at'])
                
                logger.info(f"[ALERT-NOTIFY] 🔒 Alerta {alert_id} resuelta por auto-pausa")
                
            elif not is_hysteresis and not has_exercise and new_rep_count >= 1:
                # Alertas simples se resuelven tras 1 reproducción
                alert_obj.resolution_method = 'shown'
                alert_obj.mark_resolved()
                alert_obj.save(update_fields=['resolution_method', 'resolved', 'resolved_at'])
                logger.info(f"[ALERT-NOTIFY] ✅ Alerta simple {alert_id} resuelta")

        return JsonResponse({
            'status': 'success',
            'message': 'Notificación registrada',
            'alert_id': alert_id,
            'new_repeat_count': new_rep_count,
            'session_paused': session_paused,
            'should_stop_polling': session_paused
        })

    except Exception as e:
        logger.error(f"[ALERT-NOTIFY] Error: {e}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


# Las demás funciones permanecen igual...
@login_required
@csrf_exempt
@require_http_methods(["POST"])
def acknowledge_alert(request):
    """Marca una alerta como reconocida/cerrada manualmente."""
    try:
        data = json.loads(request.body)
        alert_id = data.get('alert_id')
        resolution_method = data.get('resolution_method', 'ack')
        
        if not alert_id:
            return JsonResponse({
                'status': 'error',
                'message': 'alert_id es requerido'
            }, status=400)

        try:
            alert = AlertEvent.objects.get(id=alert_id, session__user=request.user)
        except AlertEvent.DoesNotExist:
            return JsonResponse({
                'status': 'error',
                'message': 'Alerta no encontrada'
            }, status=404)

        alert.resolved_at = timezone.now()
        alert.resolution_method = resolution_method
        alert.save(update_fields=['resolved_at', 'resolution_method'])

        try:
            if hasattr(controller, 'alert_engine') and controller.alert_engine:
                controller.alert_engine.resolve_alert(alert.alert_type)
        except Exception as engine_err:
            logger.warning(f"[ALERT] No se pudo limpiar motor: {engine_err}")

        logger.info(f"[ALERT] Alerta {alert_id} reconocida vía {resolution_method}")

        return JsonResponse({
            'status': 'success',
            'message': 'Alerta reconocida'
        })

    except Exception as e:
        logger.error(f"[ALERT] Error: {e}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    
@login_required
@csrf_exempt
@require_http_methods(["POST"])
def resolve_alert_with_exercise(request):
    """
    Resuelve una alerta al completar un ejercicio.
    Sistema simplificado sin AlertManager.
    
    Body:
    {
        "alert_id": int,
        "exercise_session_id": int
    }
    """
    try:
        data = json.loads(request.body)
        alert_id = data.get('alert_id')
        exercise_session_id = data.get('exercise_session_id')
        
        if not alert_id:
            return JsonResponse({
                'status': 'error',
                'message': 'alert_id es requerido'
            }, status=400)
        
        # Verificar alerta
        try:
            alert = AlertEvent.objects.get(id=alert_id, session__user=request.user)
        except AlertEvent.DoesNotExist:
            return JsonResponse({
                'status': 'error',
                'message': 'Alerta no encontrada'
            }, status=404)
        
        # Actualizar en BD directamente
        alert.resolved_at = timezone.now()
        alert.resolution_method = 'exercise'
        
        # Vincular sesión de ejercicio si existe
        if exercise_session_id:
            try:
                exercise_session = ExerciseSession.objects.get(
                    id=exercise_session_id,
                    user=request.user
                )
                alert.exercise_session = exercise_session
            except ExerciseSession.DoesNotExist:
                logger.warning(f"[ALERT] Sesión de ejercicio {exercise_session_id} no encontrada")
        
        alert.save()
        
        logger.info(f"[ALERT] Alerta {alert_id} resuelta con ejercicio")
        
        return JsonResponse({
            'status': 'success',
            'message': 'Alerta resuelta con ejercicio'
        })
        
    except Exception as e:
        logger.error(f"[ALERT] Error al resolver alerta con ejercicio: {e}", exc_info=True)
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def attach_exercise_to_alert(request):
    """
    Vincula una sesión de ejercicio a una alerta SIN resolverla aún.
    Sirve para ocultar la alerta mientras el ejercicio está en progreso.

    Body:
    {
        "alert_id": int,
        "exercise_session_id": int
    }
    """
    try:
        data = json.loads(request.body)
        alert_id = data.get('alert_id')
        exercise_session_id = data.get('exercise_session_id')

        if not alert_id or not exercise_session_id:
            return JsonResponse({
                'status': 'error',
                'message': 'alert_id y exercise_session_id son requeridos'
            }, status=400)

        # Verificar alerta
        try:
            alert = AlertEvent.objects.get(id=alert_id, session__user=request.user)
        except AlertEvent.DoesNotExist:
            return JsonResponse({
                'status': 'error',
                'message': 'Alerta no encontrada'
            }, status=404)

        # Verificar sesión de ejercicio
        try:
            ex_session = ExerciseSession.objects.get(id=exercise_session_id, user=request.user)
        except ExerciseSession.DoesNotExist:
            return JsonResponse({
                'status': 'error',
                'message': 'Sesión de ejercicio no encontrada'
            }, status=404)

        # Asociar sin resolver
        alert.exercise_session = ex_session
        # No tocar resolved_at ni resolution_method aquí
        alert.save(update_fields=['exercise_session'])

        return JsonResponse({
            'status': 'success',
            'message': 'Ejercicio vinculado a la alerta'
        })

    except Exception as e:
        logger.error(f"[ALERT] Error al vincular ejercicio a alerta: {e}", exc_info=True)
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def get_alert_queue_status(request):
    """
    Obtiene el estado actual del sistema de alertas (sin cola).
    Retorna si hay alguna alerta pendiente.
    """
    try:
        # Obtener sesión activa
        active_session = MonitorSession.objects.filter(
            user=request.user,
            end_time__isnull=True
        ).order_by('-start_time').first()
        
        if not active_session:
            return JsonResponse({
                'status': 'success',
                'has_alert': False,
                'pending_count': 0
            })
        
        # Contar alertas pendientes (resolved_at NULL = pendiente)
        pending_count = AlertEvent.objects.filter(
            session=active_session,
            resolved_at__isnull=True
        ).count()
        
        return JsonResponse({
            'status': 'success',
            'has_alert': pending_count > 0,
            'pending_count': pending_count
        })
        
    except Exception as e:
        logger.error(f"[ALERT] Error al obtener estado: {e}", exc_info=True)
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def cleanup_alert_queue(request):
    """
    Marca todas las alertas pendientes como resueltas (al finalizar sesión).
    """
    try:
        # Obtener sesión activa
        active_session = MonitorSession.objects.filter(
            user=request.user,
            end_time__isnull=True
        ).order_by('-start_time').first()
        
        if active_session:
            # Marcar todas las alertas pendientes como auto-resueltas
            updated = AlertEvent.objects.filter(
                session=active_session,
                resolved_at__isnull=True
            ).update(
                resolved_at=timezone.now(),
                resolution_method='auto'
            )
            
            logger.info(f"[ALERT] {updated} alertas marcadas como resueltas al finalizar sesión")
        
        return JsonResponse({
            'status': 'success',
            'message': 'Alertas limpiadas'
        })
        
    except Exception as e:
        logger.error(f"[ALERT] Error al limpiar alertas: {e}", exc_info=True)
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def audio_diagnostics(request):
    """
    Diagnóstico completo de audios de alertas.
    Verifica que todos los archivos existan, tamaños, extensiones válidas.
    """
    results = []
    summary = {
        'total': 0,
        'ok': 0,
        'missing': 0,
        'invalid_extension': 0,
        'empty': 0
    }
    
    valid_extensions = ['.mp3', '.wav', '.ogg']
    
    try:
        configs = AlertTypeConfig.objects.all()
        summary['total'] = configs.count()
        
        for config in configs:
            alert_info = {
                'alert_type': config.alert_type,
                'display_name': config.get_alert_type_display(),
                'has_audio': bool(config.default_voice_clip),
                'status': 'unknown',
                'details': {}
            }
            
            if config.default_voice_clip:
                # Obtener ruta completa del archivo
                file_path = str(config.default_voice_clip.path)
                file_url = config.default_voice_clip.url
                file_name = os.path.basename(file_path)
                file_ext = os.path.splitext(file_name)[1].lower()
                
                alert_info['details']['file_name'] = file_name
                alert_info['details']['file_url'] = file_url
                alert_info['details']['file_path'] = file_path
                alert_info['details']['extension'] = file_ext
                
                # Verificar si el archivo existe
                if os.path.exists(file_path):
                    file_size = os.path.getsize(file_path)
                    alert_info['details']['file_size'] = file_size
                    alert_info['details']['file_size_kb'] = round(file_size / 1024, 2)
                    
                    # Verificar extensión válida
                    if file_ext not in valid_extensions:
                        alert_info['status'] = 'invalid_extension'
                        alert_info['details']['error'] = f'Extensión {file_ext} no es válida. Usar: {", ".join(valid_extensions)}'
                        summary['invalid_extension'] += 1
                    # Verificar que no esté vacío
                    elif file_size == 0:
                        alert_info['status'] = 'empty'
                        alert_info['details']['error'] = 'El archivo está vacío (0 bytes)'
                        summary['empty'] += 1
                    else:
                        alert_info['status'] = 'ok'
                        summary['ok'] += 1
                else:
                    alert_info['status'] = 'missing'
                    alert_info['details']['error'] = 'Archivo no existe en el sistema de archivos'
                    summary['missing'] += 1
                    
                    # Buscar archivos similares en el directorio
                    dir_path = os.path.dirname(file_path)
                    if os.path.exists(dir_path):
                        all_files = os.listdir(dir_path)
                        suggestions = get_close_matches(file_name, all_files, n=3, cutoff=0.6)
                        if suggestions:
                            alert_info['details']['suggestions'] = suggestions
                    else:
                        alert_info['details']['error'] += ' (el directorio tampoco existe)'
            else:
                alert_info['status'] = 'no_audio'
                alert_info['details']['info'] = 'No tiene audio configurado'
            
            results.append(alert_info)
        
        return JsonResponse({
            'status': 'success',
            'summary': summary,
            'alerts': results,
            'media_root': str(settings.MEDIA_ROOT),
            'media_url': settings.MEDIA_URL
        }, json_dumps_params={'indent': 2})
        
    except Exception as e:
        logger.error(f"[AUDIO DIAGNOSTICS] Error: {e}", exc_info=True)
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)