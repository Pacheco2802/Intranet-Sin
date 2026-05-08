from django.urls import path
from . import views

app_name = 'comunicados'

urlpatterns = [
    path('', views.comunicado_list, name='list'),
    path('novo/', views.comunicado_create, name='create'),
    path('<int:pk>/', views.comunicado_detail, name='detail'),
    path('<int:pk>/editar/', views.comunicado_edit, name='edit'),
    path('<int:pk>/excluir/', views.comunicado_delete, name='delete'),
]
