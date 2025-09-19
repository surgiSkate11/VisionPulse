
from django.views.generic import TemplateView
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from apps.security.components.menu_module import MenuModule
from apps.security.components.group_session import UserGroupSession
from apps.core.models import Student, Enrollment, Assignment, Submission, Progress
from django.db.models import Avg, Count, Q


@method_decorator(login_required, name='dispatch')
class ModuloTemplateView(TemplateView):
    template_name = 'home.html'
   
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Studer - Módulos"
        context["title1"] = "Bienvenido a tu plataforma educativa Studer"
        
        # Configurar sesión de grupo si no existe
        user_session = UserGroupSession(self.request)
        user_session.set_group_session()
        
        # Aquí puedes agregar más contexto relevante para Studer si lo necesitas
        MenuModule(self.request).fill(context)
        # Extraer los menús "Herramientas" y "Sidebar" si existen
        herramientas_menu = None
        sidebar_menu = None
        for menu_item in context.get('menu_list', []):
            menu_name = getattr(menu_item['menu'], 'name', '').lower()
            if menu_name == 'herramientas':
                herramientas_menu = menu_item
            if menu_name == 'sidebar':
                sidebar_menu = menu_item
        context['herramientas_menu'] = herramientas_menu
        context['sidebar_menu'] = sidebar_menu

        # Estadísticas del estudiante logeado
        user = self.request.user
        student = getattr(user, 'student_profile', None)
        if student:
            # Cursos inscritos y completados
            total_courses = Enrollment.objects.filter(student=student).count()
            completed_courses = Enrollment.objects.filter(student=student, status='completed').count()
            # Tareas pendientes
            pending_assignments = Assignment.objects.filter(
                course__enrollments__student=student,
                is_active=True,
                is_published=True,
                submissions__student=student,
                submissions__status__in=['draft', 'returned']
            ).distinct().count()
            # Avance promedio
            avg_progress = Progress.objects.filter(student=student, progress_type='course').aggregate(
                avg=Avg('completion_percentage'))['avg'] or 0
            # Última actividad - Comentado temporalmente para evitar error de uuid
            # last_activity = Progress.objects.filter(student=student).order_by('-last_activity').first()
            last_activity = None
            context['student_stats'] = {
                'total_courses': total_courses,
                'completed_courses': completed_courses,
                'pending_assignments': pending_assignments,
                'avg_progress': round(avg_progress, 1),
                'last_activity': last_activity.last_activity if last_activity else None,
            }
        else:
            context['student_stats'] = None
        return context