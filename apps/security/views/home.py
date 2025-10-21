
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from apps.security.components.sidebar_menu_mixin import SidebarMenuMixin


class HomeView(LoginRequiredMixin, SidebarMenuMixin, TemplateView):
    template_name = 'home.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Dashboard'
        
        # user = self.request.user
        # student = getattr(user, 'student_profile', None)
        # if student:
        #     # Cursos inscritos y completados
        #     total_courses = Enrollment.objects.filter(student=student).count()
        #     completed_courses = Enrollment.objects.filter(student=student, status='completed').count()
        #     # Tareas pendientes
        #     pending_assignments = Assignment.objects.filter(
        #         course__enrollments__student=student,
        #         is_active=True,
        #         is_published=True,
        #         submissions__student=student,
        #         submissions__status__in=['draft', 'returned']
        #     ).distinct().count()
        #     # Avance promedio
        #     avg_progress = Progress.objects.filter(student=student, progress_type='course').aggregate(
        #         avg=Avg('completion_percentage'))['avg'] or 0
        #     # Última actividad
        #     last_activity = None
        #     context['student_stats'] = {
        #         'total_courses': total_courses,
        #         'completed_courses': completed_courses,
        #         'pending_assignments': pending_assignments,
        #         'avg_progress': round(avg_progress, 1),
        #         'last_activity': last_activity.last_activity if last_activity else None,
        #     }
        # else:
        #     context['student_stats'] = None
        return context