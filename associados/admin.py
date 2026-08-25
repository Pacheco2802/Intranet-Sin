from django.contrib import admin

from .models import Associado, Caso, CasoDocumento


@admin.register(Associado)
class AssociadoAdmin(admin.ModelAdmin):
    list_display = ('nome', 'email', 'cargo', 'empregador', 'origem', 'updated_at')
    list_filter = ('origem',)
    search_fields = ('nome', 'email', 'cpf_hash')
    readonly_fields = ('cpf_hash', 'created_at', 'updated_at')


class CasoDocumentoInline(admin.TabularInline):
    model = CasoDocumento
    extra = 0


@admin.register(Caso)
class CasoAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'associado', 'tipo', 'status', 'departamento_responsavel', 'updated_at')
    list_filter = ('tipo', 'status', 'departamento_responsavel')
    search_fields = ('titulo', 'associado__nome')
    autocomplete_fields = ('associado',)
    filter_horizontal = ('atendimentos',)
    inlines = [CasoDocumentoInline]


@admin.register(CasoDocumento)
class CasoDocumentoAdmin(admin.ModelAdmin):
    list_display = ('nome_original', 'caso', 'tipo', 'enviado_por', 'created_at')
    list_filter = ('tipo',)
    search_fields = ('nome_original', 'caso__titulo')
