from django.urls import path
from . import public_views

app_name = 'triagem'

urlpatterns = [
    path('', public_views.triagem_entrada, name='entrada'),
    path('t/<str:token>/', public_views.triagem_token, name='token'),
    path('ok/', public_views.triagem_ok, name='ok'),
    path('privacidade/', public_views.triagem_privacidade, name='privacidade'),
]
