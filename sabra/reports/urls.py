from django.urls import path
from . import views

app_name = 'reports'

urlpatterns = [
    # Reports dashboard
    path('', views.ReportDashboardView.as_view(), name='dashboard'),
    
    # Generated reports
    path('history/', views.ReportHistoryView.as_view(), name='history'),
    path('view/<int:pk>/', views.ReportDetailView.as_view(), name='view'),
    
    # Generate reports
    path('generate/backup-summary/', views.BackupSummaryView.as_view(), name='backup_summary'),
    path('generate/changes/', views.ChangeReportView.as_view(), name='change_report'),
    path('generate/failures/', views.FailureReportView.as_view(), name='failure_report'),
    path('generate/device-status/', views.DeviceStatusView.as_view(), name='device_status'),
    
    # Export
    path('export/<int:pk>/csv/', views.ExportCSVView.as_view(), name='export_csv'),
    
    # Scheduled reports
    path('scheduled/', views.ScheduledReportListView.as_view(), name='scheduled_list'),
    path('scheduled/create/', views.ScheduledReportCreateView.as_view(), name='scheduled_create'),
    path('scheduled/<int:pk>/edit/', views.ScheduledReportUpdateView.as_view(), name='scheduled_edit'),
    path('scheduled/<int:pk>/delete/', views.ScheduledReportDeleteView.as_view(), name='scheduled_delete'),
]
