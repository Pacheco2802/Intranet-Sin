from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from core import views as core_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('service-worker.js', core_views.pwa_service_worker, name='pwa_service_worker'),
    path('manifest.webmanifest', core_views.pwa_manifest, name='pwa_manifest'),
    path('', include('core.urls')),
    path('mensagens/', include('mensagens.urls')),
    path('kanban/', include('kanban.urls')),
    path('comunicados/', include('comunicados.urls')),
    path('atendimento/', include('atendimento.urls')),
    path('triagem/', include('atendimento.urls_public')),
    path('chamados/', include('chamados.urls')),
    path('associados/', include('associados.urls')),
    path('agenda/', include('agenda.urls')),
    path('consultas/', include('consultas.urls')),
    path('financeiro/', include('financeiro.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
