from django.urls import path
from . import views

app_name = 'mensagens'

urlpatterns = [
    path('', views.inbox, name='inbox'),
    path('nova/', views.new_conversation, name='new_conversation'),
    path('<int:pk>/', views.conversation, name='conversation'),
    path('<int:pk>/poll/', views.messages_poll, name='messages_poll'),
    path('<int:pk>/mais/', views.messages_load_more, name='load_more'),
    path('<int:pk>/enviar/', views.send_message, name='send_message'),
    path('mensagem/<int:pk>/apagar/', views.delete_message, name='delete_message'),
]
