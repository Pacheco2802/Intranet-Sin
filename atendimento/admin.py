from django.contrib import admin

from .models import Atendimento, AtendimentoEtapa, AtendimentoAnexo, TriagemPublica


@admin.register(Atendimento)
class AtendimentoAdmin(admin.ModelAdmin):
    list_display = ('nome_filiado', 'assunto', 'nextqs_fila', 'numero_senha',
                    'status', 'departamento_atual', 'created_at')
    list_filter = ('status', 'nextqs_fila', 'departamento_atual', 'is_auto_nextqs')
    search_fields = ('nome_filiado', 'assunto', 'numero_senha', 'cpf_hash', 'triagem_codigo')
    readonly_fields = ('cpf_hash', 'triagem_token', 'triagem_codigo',
                       'triagem_preenchida_em', 'created_at', 'updated_at')
    date_hierarchy = 'created_at'


@admin.register(TriagemPublica)
class TriagemPublicaAdmin(admin.ModelAdmin):
    list_display = ('atendimento', 'motivo', 'origem', 'lgpd_consent', 'created_at')
    list_filter = ('motivo', 'origem')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(AtendimentoEtapa)
class AtendimentoEtapaAdmin(admin.ModelAdmin):
    list_display = ('atendimento', 'tipo', 'autor', 'created_at')
    list_filter = ('tipo',)


@admin.register(AtendimentoAnexo)
class AtendimentoAnexoAdmin(admin.ModelAdmin):
    list_display = ('nome_original', 'atendimento', 'enviado_por', 'created_at')
