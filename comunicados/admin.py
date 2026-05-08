from django.contrib import admin
from .models import Comunicado


@admin.register(Comunicado)
class ComunicadoAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'is_published', 'is_pinned', 'published_at', 'expires_at')
    list_filter = ('is_published', 'is_pinned')
    search_fields = ('title', 'content')
    filter_horizontal = ('departments',)
    actions = ['publish_selected']

    def publish_selected(self, request, queryset):
        for c in queryset:
            c.publish()
    publish_selected.short_description = 'Publicar selecionados'
