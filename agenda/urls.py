from django.urls import path
from . import views

app_name = 'agenda'

urlpatterns = [
    path('', views.event_list, name='event_list'),
    path('novo/', views.event_create, name='event_create'),
    path('<int:pk>/', views.event_detail, name='event_detail'),
    path('<int:pk>/editar/', views.event_edit, name='event_edit'),
    path('<int:pk>/excluir/', views.event_delete, name='event_delete'),
    path('<int:pk>/confirmar/', views.event_confirm, name='event_confirm'),
    path('<int:pk>/documentos/upload/', views.evento_documento_upload, name='documento_upload'),
    path('documentos/<int:doc_pk>/excluir/', views.evento_documento_delete, name='documento_delete'),
]
