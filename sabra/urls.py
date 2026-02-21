"""
Sabra Device Backup - URL Configuration
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from sabra.views import (
    DashboardView, LogsView, LogsAPIView, LogsClearView,
    AppExportView, AppExportDownloadView,
    AppImportView, AppImportProcessView, AppImportZipView,
)

urlpatterns = [
    # Admin site
    path('admin/', admin.site.urls),
    
    # Dashboard (home)
    path('', DashboardView.as_view(), name='dashboard'),
    
    # System Logs
    path('logs/', LogsView.as_view(), name='logs'),
    path('logs/api/', LogsAPIView.as_view(), name='logs_api'),
    path('logs/clear/', LogsClearView.as_view(), name='logs_clear'),
    
    # App Import/Export (CSV data)
    path('export/', AppExportView.as_view(), name='app_export'),
    path('export/download/<str:export_type>/', AppExportDownloadView.as_view(), name='app_export_download'),
    path('import/', AppImportView.as_view(), name='app_import'),
    path('import/process/', AppImportProcessView.as_view(), name='app_import_process'),
    path('import/zip/', AppImportZipView.as_view(), name='app_import_zip'),
    
    # System Backup & Restore (new encrypted backup system)
    path('system-backup/', include('sabra.system_backup.urls', namespace='system_backup')),
    
    # Apps
    path('accounts/', include('sabra.accounts.urls')),
    path('inventory/', include('sabra.inventory.urls')),
    path('backups/', include('sabra.backups.urls')),
    path('activities/', include('sabra.activities.urls')),
    path('reports/', include('sabra.reports.urls')),
    path('mailconfig/', include('sabra.mailconfig.urls')),
]

# Serve static and media files in development
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    
    # Debug toolbar (optional)
    try:
        import debug_toolbar
        urlpatterns = [
            path('__debug__/', include(debug_toolbar.urls)),
        ] + urlpatterns
    except ImportError:
        pass

# Customize admin site
admin.site.site_header = 'Sabra Device Backup'
admin.site.site_title = 'Sabra Admin'
admin.site.index_title = 'Device Backup Administration'
