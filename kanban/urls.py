from django.urls import path
from . import views

app_name = 'kanban'

urlpatterns = [
    path('', views.board_list, name='board_list'),
    path('analise/', views.analise, name='analise'),
    path('novo/', views.board_create, name='board_create'),
    path('<int:pk>/', views.board_detail, name='board_detail'),
    path('<int:pk>/editar/', views.board_edit, name='board_edit'),
    path('<int:pk>/excluir/', views.board_delete, name='board_delete'),
    path('<int:pk>/acesso/', views.board_access, name='board_access'),
    path('<int:board_pk>/coluna/nova/', views.column_create, name='column_create'),
    path('<int:board_pk>/coluna/<int:pk>/editar/', views.column_edit, name='column_edit'),
    path('<int:board_pk>/coluna/<int:pk>/excluir/', views.column_delete, name='column_delete'),
    path('<int:board_pk>/card/novo/', views.card_create, name='card_create'),
    path('<int:board_pk>/card/<int:pk>/', views.card_detail, name='card_detail'),
    path('<int:board_pk>/card/<int:pk>/editar/', views.card_edit, name='card_edit'),
    path('<int:board_pk>/card/<int:pk>/excluir/', views.card_delete, name='card_delete'),
    path('card/<int:pk>/mover/', views.card_move, name='card_move'),
    path('subtarefa/<int:pk>/toggle/', views.subtask_toggle, name='subtask_toggle'),
    path('subtarefa/<int:pk>/excluir/', views.subtask_delete, name='subtask_delete'),
    path('subtarefa/<int:pk>/anexar/', views.subtask_attach, name='subtask_attach'),
]
