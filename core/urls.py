from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('registro/', views.register_view, name='register'),
    path('perfil/', views.profile, name='profile'),

    path('lgpd/consentimento/', views.lgpd_consent, name='lgpd_consent'),
    path('lgpd/politica/', views.lgpd_policy, name='lgpd_policy'),
    path('lgpd/exportar/', views.lgpd_export, name='lgpd_export'),

    path('usuarios/', views.user_list, name='user_list'),
    path('usuarios/novo/', views.user_create, name='user_create'),
    path('usuarios/<int:pk>/editar/', views.user_edit, name='user_edit'),
    path('usuarios/<int:pk>/desativar/', views.user_deactivate, name='user_deactivate'),
    path('usuarios/<int:pk>/aprovar/', views.user_approve, name='user_approve'),
    path('usuarios/<int:pk>/rejeitar/', views.user_reject, name='user_reject'),

    path('departamentos/', views.department_list, name='department_list'),
    path('departamentos/novo/', views.department_create, name='department_create'),
    path('departamentos/<int:pk>/editar/', views.department_edit, name='department_edit'),

    path('equipes/', views.team_list, name='team_list'),
    path('equipes/nova/', views.team_create, name='team_create'),
    path('equipes/<int:pk>/editar/', views.team_edit, name='team_edit'),
    path('equipes/<int:pk>/excluir/', views.team_delete, name='team_delete'),
    path('equipes/<int:pk>/chat/', views.team_chat, name='team_chat'),
    path('equipes/<int:pk>/adicionar/', views.team_add_member, name='team_add_member'),
    path('equipes/<int:pk>/remover/<int:user_id>/', views.team_remove_member, name='team_remove_member'),

    path('notificacoes/', views.notification_list, name='notification_list'),
    path('notificacoes/<int:pk>/lida/', views.notification_mark_read, name='notification_mark_read'),
    path('notificacoes/marcar-todas/', views.notification_mark_all_read, name='notification_mark_all_read'),
]
