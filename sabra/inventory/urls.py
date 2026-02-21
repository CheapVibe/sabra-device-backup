from django.urls import path
from . import views

app_name = 'inventory'

urlpatterns = [
    # Devices
    path('devices/', views.DeviceListView.as_view(), name='device_list'),
    path('devices/create/', views.DeviceCreateView.as_view(), name='device_create'),
    path('devices/<int:pk>/', views.DeviceDetailView.as_view(), name='device_detail'),
    path('devices/<int:pk>/edit/', views.DeviceUpdateView.as_view(), name='device_edit'),
    path('devices/<int:pk>/delete/', views.DeviceDeleteView.as_view(), name='device_delete'),
    path('devices/<int:pk>/copy/', views.DeviceCopyView.as_view(), name='device_copy'),
    path('devices/bulk-action/', views.DeviceBulkActionView.as_view(), name='device_bulk_action'),
    
    # Credential Profiles
    path('credentials/', views.CredentialListView.as_view(), name='credential_list'),
    path('credentials/create/', views.CredentialCreateView.as_view(), name='credential_create'),
    path('credentials/<int:pk>/', views.CredentialDetailView.as_view(), name='credential_detail'),
    path('credentials/<int:pk>/edit/', views.CredentialUpdateView.as_view(), name='credential_edit'),
    path('credentials/<int:pk>/delete/', views.CredentialDeleteView.as_view(), name='credential_delete'),
    
    # Device Groups
    path('groups/', views.GroupListView.as_view(), name='group_list'),
    path('groups/create/', views.GroupCreateView.as_view(), name='group_create'),
    path('groups/<int:pk>/', views.GroupDetailView.as_view(), name='group_detail'),
    path('groups/<int:pk>/edit/', views.GroupUpdateView.as_view(), name='group_edit'),
    path('groups/<int:pk>/delete/', views.GroupDeleteView.as_view(), name='group_delete'),
    
    # Vendors
    path('vendors/', views.VendorListView.as_view(), name='vendor_list'),
    path('vendors/create/', views.VendorCreateView.as_view(), name='vendor_create'),
    path('vendors/<int:pk>/', views.VendorDetailView.as_view(), name='vendor_detail'),
    path('vendors/<int:pk>/edit/', views.VendorUpdateView.as_view(), name='vendor_edit'),
    path('vendors/<int:pk>/delete/', views.VendorDeleteView.as_view(), name='vendor_delete'),
]
