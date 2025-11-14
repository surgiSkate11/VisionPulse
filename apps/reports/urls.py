from django.urls import path
from . import views

app_name = 'reports'

urlpatterns = [
    path('', views.DashboardView.as_view(), name='dashboard'),
    path('list/', views.ReportListView.as_view(), name='report_list'),
    path('api/data/', views.ReportDataView.as_view(), name='api_data'),
    path('export/', views.ExportReportView.as_view(), name='export'),
]