"""
URL configuration for System Backup.
"""

from django.urls import path
from .views import (
    SystemBackupDashboardView,
    SystemBackupCreateView,
    SystemBackupUploadView,
    SystemBackupPreviewView,
    SystemBackupConfirmView,
    SystemBackupRestoreView,
    SystemBackupResultsView,
    SystemBackupCancelView,
    SystemBackupEstimateView,
)

app_name = 'system_backup'

urlpatterns = [
    path('', SystemBackupDashboardView.as_view(), name='dashboard'),
    path('create/', SystemBackupCreateView.as_view(), name='create'),
    path('upload/', SystemBackupUploadView.as_view(), name='upload'),
    path('preview/', SystemBackupPreviewView.as_view(), name='preview'),
    path('confirm/', SystemBackupConfirmView.as_view(), name='confirm'),
    path('restore/', SystemBackupRestoreView.as_view(), name='restore'),
    path('results/', SystemBackupResultsView.as_view(), name='results'),
    path('cancel/', SystemBackupCancelView.as_view(), name='cancel'),
    path('estimate/', SystemBackupEstimateView.as_view(), name='estimate'),
]
