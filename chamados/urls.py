from django.urls import path
from . import views

app_name = 'chamados'

urlpatterns = [
    path('', views.meus_chamados, name='meus'),
    path('abrir/', views.chamado_abrir, name='abrir'),
    path('abrir/passo/', views.triagem_passo, name='triagem_passo'),
    path('abrir/criar/', views.chamado_criar, name='criar'),
    path('painel/', views.painel, name='painel'),
    path('<int:pk>/', views.chamado_detail, name='detail'),
]
