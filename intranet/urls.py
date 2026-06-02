from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('core.urls')),
    path('mensagens/', include('mensagens.urls')),
    path('kanban/', include('kanban.urls')),
    path('comunicados/', include('comunicados.urls')),
    path('atendimento/', include('atendimento.urls')),
    path('agenda/', include('agenda.urls')),
    path('consultas/', include('consultas.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
