from django.urls import path
from . import views

app_name = 'activities'

urlpatterns = [
    # Activity Sessions
    path('', views.SessionListView.as_view(), name='session_list'),
    path('run/', views.RunCommandView.as_view(), name='run_command'),
    path('session/<int:pk>/', views.SessionDetailView.as_view(), name='session_detail'),
    path('session/<int:pk>/results/', views.SessionResultsView.as_view(), name='session_results'),
    
    # Command Results / Output
    path('result/<int:pk>/', views.CommandResultDetailView.as_view(), name='result_detail'),
    path('result/diff/<int:pk1>/<int:pk2>/', views.CommandResultDiffView.as_view(), name='result_diff'),
    path('output/compare/', views.CommandOutputCompareView.as_view(), name='output_compare'),
    
    # Command Templates
    path('templates/', views.TemplateListView.as_view(), name='template_list'),
    path('templates/create/', views.TemplateCreateView.as_view(), name='template_create'),
    path('templates/<int:pk>/edit/', views.TemplateUpdateView.as_view(), name='template_edit'),
    path('templates/<int:pk>/delete/', views.TemplateDeleteView.as_view(), name='template_delete'),
]
