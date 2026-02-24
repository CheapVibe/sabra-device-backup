from django.urls import path
from . import views
from . import api

app_name = 'backups'

urlpatterns = [
    # Backup Jobs
    path('jobs/', views.JobListView.as_view(), name='job_list'),
    path('jobs/create/', views.JobCreateView.as_view(), name='job_create'),
    path('jobs/<int:pk>/', views.JobDetailView.as_view(), name='job_detail'),
    path('jobs/<int:pk>/edit/', views.JobUpdateView.as_view(), name='job_edit'),
    path('jobs/<int:pk>/delete/', views.JobDeleteView.as_view(), name='job_delete'),
    path('jobs/<int:pk>/copy/', views.JobCopyView.as_view(), name='job_copy'),
    path('jobs/<int:pk>/run/', views.JobRunView.as_view(), name='job_run'),
    path('jobs/<int:pk>/toggle/', views.JobToggleView.as_view(), name='job_toggle'),
    
    # Job Executions
    path('executions/', views.ExecutionListView.as_view(), name='execution_list'),
    path('executions/<int:pk>/', views.ExecutionDetailView.as_view(), name='execution_detail'),
    
    # Execution API (real-time progress)
    path('api/executions/<int:pk>/progress/', api.ExecutionProgressAPIView.as_view(), name='execution_progress_api'),
    path('api/executions/<int:pk>/snapshots/', api.ExecutionSnapshotsAPIView.as_view(), name='execution_snapshots_api'),
    
    # Config Snapshots
    path('snapshots/', views.SnapshotListView.as_view(), name='snapshot_list'),
    path('snapshots/<int:pk>/', views.SnapshotDetailView.as_view(), name='snapshot_detail'),
    path('snapshots/<int:pk>/view/', views.SnapshotViewView.as_view(), name='snapshot_view'),
    path('snapshots/<int:pk>/download/', views.SnapshotDownloadView.as_view(), name='snapshot_download'),
    path('snapshots/<int:pk>/diff/', views.SnapshotDiffView.as_view(), name='snapshot_diff'),
    path('snapshots/compare/', views.SnapshotCompareSelectorView.as_view(), name='compare_selector'),
    path('snapshots/compare/<int:pk1>/<int:pk2>/', views.SnapshotCompareView.as_view(), name='snapshot_compare'),
    path('snapshots/<int:pk>/protect/', views.SnapshotProtectView.as_view(), name='snapshot_protect'),
    path('snapshots/<int:pk>/restore/', views.SnapshotRestoreView.as_view(), name='snapshot_restore'),
    
    # Quick/Ad-hoc backup
    path('quick/', views.QuickBackupView.as_view(), name='quick_backup'),
    path('device/<int:pk>/backup/', views.DeviceBackupView.as_view(), name='device_backup'),
    
    # Export/Import Configurations
    path('export/', views.ExportConfigView.as_view(), name='export_config'),
    path('import/', views.ImportConfigView.as_view(), name='import_config'),
    path('import/review/', views.ImportConfigReviewView.as_view(), name='import_config_review'),
    
    # Export/Import Inventory
    path('export/inventory/', views.ExportInventoryView.as_view(), name='export_inventory'),
    path('import/inventory/', views.ImportInventoryView.as_view(), name='import_inventory'),
    
    # Additional Command Outputs
    path('additional/device/<int:device_id>/', views.AdditionalOutputListView.as_view(), name='additional_output_list'),
    path('additional/<int:pk>/', views.AdditionalOutputDetailView.as_view(), name='additional_output_detail'),
    path('additional/<int:pk>/view/', views.AdditionalOutputViewView.as_view(), name='additional_output_view'),
    path('additional/<int:pk>/download/', views.AdditionalOutputDownloadView.as_view(), name='additional_output_download'),
    path('additional/<int:pk>/diff/', views.AdditionalOutputDiffView.as_view(), name='additional_output_diff'),
    path('additional/latest/<int:device_id>/', views.LatestAdditionalOutputView.as_view(), name='additional_output_latest'),
    
    # Retention Policy
    path('retention/', views.RetentionSettingsView.as_view(), name='retention_settings'),
    path('retention/history/', views.RetentionHistoryView.as_view(), name='retention_history'),
    path('retention/history/<int:pk>/', views.RetentionExecutionDetailView.as_view(), name='retention_execution_detail'),
    path('retention/preview/', views.RetentionPreviewView.as_view(), name='retention_preview'),
    path('retention/run/', views.RetentionRunView.as_view(), name='retention_run'),
    path('retention/deleted/', views.RetentionDeletedSnapshotsView.as_view(), name='retention_deleted_snapshots'),
]
