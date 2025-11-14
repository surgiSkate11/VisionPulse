from django.core.management.base import BaseCommand
from django.core.files.storage import default_storage
from django.utils.termcolors import make_style
import json

from apps.monitoring.models import AlertExerciseMapping, AlertTypeConfig

EXERCISE_ALERT_TYPES = [
    'microsleep',
    'fatigue',
    'low_blink_rate',
    'high_blink_rate',
    'frequent_distraction',
    'micro_rhythm',
    'head_tension',
]


class Command(BaseCommand):
    help = (
        "Muestra el estado de integración de las alertas de ejercicio: "
        "mapeo a ejercicio, activo, prioridad, config de tipo y audio disponible.\n"
        "Usa --json para salida en JSON."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--json', action='store_true', dest='as_json', default=False,
            help='Imprime el resultado en formato JSON'
        )
        parser.add_argument(
            '--all', action='store_true', dest='include_all', default=False,
            help='Incluye todos los tipos definidos en AlertExerciseMapping en vez de solo los 7 de ejercicio'
        )

    def _audio_status(self, alert_type: str, cfg: AlertTypeConfig):
        """Determina si existe un audio disponible (configurado o fallback en media/monitoring/alerts/types/<type>.mp3)."""
        configured = False
        configured_path = None
        fallback = False
        fallback_path = f"monitoring/alerts/types/{alert_type}.mp3"

        try:
            if cfg and cfg.default_voice_clip:
                configured_path = cfg.default_voice_clip.name
                configured = default_storage.exists(configured_path)
        except Exception:
            configured = False

        try:
            fallback = default_storage.exists(fallback_path)
        except Exception:
            fallback = False

        return {
            'configured': bool(configured),
            'configured_path': configured_path,
            'fallback': bool(fallback),
            'fallback_path': fallback_path,
            'audio_ok': bool(configured or fallback),
        }

    def handle(self, *args, **options):
        as_json = options['as_json']
        include_all = options['include_all']

        if include_all:
            types = list(
                AlertExerciseMapping.objects.order_by('priority', 'alert_type').values_list('alert_type', flat=True)
            )
            if not types:
                types = EXERCISE_ALERT_TYPES
        else:
            types = EXERCISE_ALERT_TYPES

        rows = []
        for t in types:
            mapping = AlertExerciseMapping.objects.filter(alert_type=t).select_related('exercise').first()
            cfg = AlertTypeConfig.objects.filter(alert_type=t).first()

            exercise_id = getattr(getattr(mapping, 'exercise', None), 'id', None)
            exercise_title = getattr(getattr(mapping, 'exercise', None), 'title', None)
            is_active = getattr(mapping, 'is_active', False)
            priority = getattr(mapping, 'priority', None)

            has_cfg = bool(cfg)
            cfg_active = bool(getattr(cfg, 'is_active', False)) if cfg else False
            cfg_desc = getattr(cfg, 'description', None) if cfg else None

            audio = self._audio_status(t, cfg)

            ok = bool(mapping and exercise_id and is_active and has_cfg and cfg_active and audio['audio_ok'])

            rows.append({
                'type': t,
                'mapping_exists': bool(mapping),
                'exercise_id': exercise_id,
                'exercise_title': exercise_title,
                'mapping_active': is_active,
                'priority': priority,
                'type_config_exists': has_cfg,
                'type_config_active': cfg_active,
                'type_config_description': cfg_desc,
                'audio': audio,
                'ok': ok,
            })

        if as_json:
            self.stdout.write(json.dumps(rows, ensure_ascii=False, indent=2))
            return

        # Pretty console output
        title_style = make_style(opts=('bold',))
        ok_style = make_style(fg='green', opts=('bold',))
        warn_style = make_style(fg='yellow')
        err_style = make_style(fg='red', opts=('bold',))

        self.stdout.write(title_style('Verificando mapeos y configuraciones de alertas de ejercicio'))
        self.stdout.write('')

        all_ok = True
        for r in rows:
            ok_mark = '✓' if r['ok'] else '✗'
            style = ok_style if r['ok'] else err_style
            self.stdout.write(style(f"[{ok_mark}] {r['type']}"))
            self.stdout.write(f"  - Mapping: {'sí' if r['mapping_exists'] else 'no'} | activo: {'sí' if r['mapping_active'] else 'no'} | prioridad: {r['priority']}")
            self.stdout.write(f"  - Exercise: {r['exercise_title'] or '—'} (id: {r['exercise_id'] or '—'})")
            self.stdout.write(f"  - TypeConfig: {'sí' if r['type_config_exists'] else 'no'} | activo: {'sí' if r['type_config_active'] else 'no'} | desc: {r['type_config_description'] or '—'}")
            aud = r['audio']
            aud_line = f"configurado: {'sí' if aud['configured'] else 'no'}"
            if aud['configured_path']:
                aud_line += f" ({aud['configured_path']})"
            aud_line += f" | fallback: {'sí' if aud['fallback'] else 'no'} ({aud['fallback_path']})"
            self.stdout.write(f"  - Audio: {aud_line}")
            self.stdout.write('')
            if not r['ok']:
                all_ok = False

        if all_ok:
            self.stdout.write(ok_style('✓ Integración OK: todas las alertas de ejercicio están listas.'))
        else:
            self.stdout.write(warn_style('Algunas alertas no cumplen todos los requisitos. Revisa las líneas marcadas con ✗.'))
