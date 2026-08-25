from django.urls import path
from . import views

app_name = 'associados'

urlpatterns = [
    path('', views.associado_list, name='list'),
    path('<int:pk>/', views.associado_detail, name='detail'),
    path('<int:pk>/editar/', views.associado_edit, name='edit'),
    path('<int:pk>/casos/novo/', views.caso_create, name='caso_create'),
    path('casos/<int:pk>/', views.caso_detail, name='caso_detail'),
    path('casos/<int:pk>/editar/', views.caso_edit, name='caso_edit'),
]
