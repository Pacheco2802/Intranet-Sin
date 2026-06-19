from django.contrib import admin

from .models import (
    ParametroFinanceiro,
    Reembolso,
    AtividadeDiretoria,
    PagamentoDiretoria,
)


@admin.register(ParametroFinanceiro)
class ParametroFinanceiroAdmin(admin.ModelAdmin):
    list_display = ('valor_hora_diretoria_padrao', 'teto_horas_mensal', 'updated_at')

    def has_add_permission(self, request):
        # Singleton: só permite adicionar se ainda não existir
        return not ParametroFinanceiro.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Reembolso)
class ReembolsoAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'solicitante', 'valor', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('titulo', 'descricao', 'solicitante__first_name', 'solicitante__last_name', 'solicitante__email')
    readonly_fields = ('created_at', 'updated_at', 'pago_em')
    date_hierarchy = 'created_at'


@admin.register(AtividadeDiretoria)
class AtividadeDiretoriaAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'diretor', 'data_atividade', 'horas', 'status', 'competencia')
    list_filter = ('status', 'competencia')
    search_fields = ('titulo', 'descricao', 'diretor__first_name', 'diretor__last_name', 'diretor__email')
    readonly_fields = ('competencia', 'created_at', 'updated_at', 'aprovado_em')
    date_hierarchy = 'data_atividade'


@admin.register(PagamentoDiretoria)
class PagamentoDiretoriaAdmin(admin.ModelAdmin):
    list_display = ('diretor', 'competencia', 'horas_pagas', 'valor_hora', 'valor_total', 'pago_por', 'pago_em')
    list_filter = ('competencia',)
    search_fields = ('diretor__first_name', 'diretor__last_name', 'diretor__email')
    readonly_fields = ('created_at',)
    date_hierarchy = 'competencia'
