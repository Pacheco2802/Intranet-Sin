from django.urls import path
from . import views

app_name = 'consultas'

urlpatterns = [
    path('',                                views.agenda,              name='agenda'),
    path('nova/',                           views.consulta_create,     name='consulta_create'),
    path('<int:pk>/',                       views.consulta_detail,     name='consulta_detail'),
    path('<int:pk>/editar/',               views.consulta_edit,       name='consulta_edit'),
    path('<int:pk>/status/',               views.consulta_status,     name='consulta_status'),
    path('<int:pk>/remarcar/',             views.consulta_reschedule, name='consulta_reschedule'),
    path('<int:pk>/excluir/',              views.consulta_delete,     name='consulta_delete'),
    path('<int:pk>/prontuario/',           views.prontuario_save,     name='prontuario_save'),
    path('<int:pk>/documentos/upload/',    views.documento_upload,    name='documento_upload'),
    path('<int:pk>/aso/',                  views.aso_edit,            name='aso_edit'),
    path('documentos/<int:doc_pk>/excluir/', views.documento_delete,  name='documento_delete'),
    path('medicos/',                       views.doctor_list,         name='doctor_list'),
    path('medicos/novo/',                  views.doctor_create,       name='doctor_create'),
    path('medicos/<int:pk>/editar/',       views.doctor_edit,         name='doctor_edit'),
]
