from django.urls import path
from . import views

app_name = 'atendimento'

urlpatterns = [
    path('', views.atendimento_list, name='list'),
    path('novo/', views.atendimento_create, name='create'),
    path('<int:pk>/', views.atendimento_detail, name='detail'),
]
