from django.urls import path

from . import views

app_name = 'financeiro'

urlpatterns = [
    path('', views.home, name='home'),

    # Painel de pagamentos
    path('pagamentos/', views.pagamentos, name='pagamentos'),
    path('diretoria/pagar/', views.diretoria_pagar, name='diretoria_pagar'),
    path('diretoria/pagar-lote/', views.diretoria_pagar_lote, name='diretoria_pagar_lote'),

    # Reembolsos
    path('reembolsos/', views.reembolso_list, name='reembolso_list'),
    path('reembolsos/novo/', views.reembolso_create, name='reembolso_create'),
    path('reembolsos/<int:pk>/', views.reembolso_detail, name='reembolso_detail'),
    path('reembolsos/<int:pk>/rejeitar/', views.reembolso_rejeitar, name='reembolso_rejeitar'),
    path('reembolsos/<int:pk>/pagar/', views.reembolso_pagar, name='reembolso_pagar'),

    # Configuração de diretores (valor/hora por diretor + parâmetros globais)
    path('configuracoes/', views.diretor_config, name='diretor_config'),

    # Atividades de diretoria
    path('diretoria/', views.atividade_list, name='atividade_list'),
    path('diretoria/nova/', views.atividade_create, name='atividade_create'),
    path('diretoria/<int:pk>/', views.atividade_detail, name='atividade_detail'),
    path('diretoria/<int:pk>/editar/', views.atividade_editar, name='atividade_editar'),
    path('diretoria/<int:pk>/excluir/', views.atividade_excluir, name='atividade_excluir'),
    path('diretoria/<int:pk>/aprovar/', views.atividade_aprovar, name='atividade_aprovar'),
    path('diretoria/diretor/<int:diretor_pk>/aprovar-todas/', views.atividade_aprovar_diretor, name='atividade_aprovar_diretor'),
    path('diretoria/<int:pk>/rejeitar/', views.atividade_rejeitar, name='atividade_rejeitar'),
]
