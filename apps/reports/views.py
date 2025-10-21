from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from apps.security.components.sidebar_menu_mixin import SidebarMenuMixin

class ReportListView(LoginRequiredMixin, SidebarMenuMixin, TemplateView):
    template_name = 'reports/report_list.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['section'] = 'reports'
        return context
