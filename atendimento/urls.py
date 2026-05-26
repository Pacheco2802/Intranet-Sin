from django.urls import path
from . import views

app_name = 'atendimento'

urlpatterns = [
    path('', views.atendimento_list, name='list'),
    path('novo/', views.atendimento_create, name='create'),
    path('painel/', views.atendimento_painel, name='painel'),
    path('metricas/', views.atendimento_metricas, name='metricas'),
    path('cpf-lookup/', views.atendimento_cpf_lookup, name='cpf_lookup'),
    path('filiado/<str:cpf_hash>/', views.atendimento_filiado, name='filiado'),
    path('<int:pk>/', views.atendimento_detail, name='detail'),
    path('<int:pk>/chamar/', views.nextqs_chamar, name='nextqs_chamar'),
    path('<int:pk>/imprimir/', views.atendimento_imprimir_senha, name='imprimir_senha'),
]
