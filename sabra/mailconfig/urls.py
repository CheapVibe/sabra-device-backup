from django.urls import path
from . import views

app_name = 'mailconfig'

urlpatterns = [
    # Main settings page (singleton)
    path('', views.MailConfigView.as_view(), name='settings'),
    
    # Legacy routes (redirect to settings)
    path('list/', views.ConfigListView.as_view(), name='config_list'),
    path('create/', views.ConfigCreateView.as_view(), name='config_create'),
    path('<int:pk>/', views.ConfigDetailView.as_view(), name='config_detail'),
    path('<int:pk>/edit/', views.ConfigUpdateView.as_view(), name='config_edit'),
    path('<int:pk>/delete/', views.ConfigDeleteView.as_view(), name='config_delete'),
    path('<int:pk>/test/', views.ConfigTestView.as_view(), name='config_test'),
    path('<int:pk>/activate/', views.ConfigActivateView.as_view(), name='config_activate'),
    path('test/', views.ConfigTestView.as_view(), name='test'),
    
    # Send test email
    path('send-test/', views.SendTestEmailView.as_view(), name='send_test'),
    
    # Status
    path('status/', views.StatusView.as_view(), name='status'),
]
