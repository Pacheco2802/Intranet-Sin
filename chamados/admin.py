from django.contrib import admin

from .models import (
    CategoriaChamado, PerguntaTriagem, OpcaoTriagem,
    Chamado, ChamadoEtapa, ChamadoAnexo,
)


@admin.register(CategoriaChamado)
class CategoriaChamadoAdmin(admin.ModelAdmin):
    list_display = ('nome', 'icone', 'prioridade_padrao', 'sla_horas', 'responsavel_padrao', 'ativo', 'ordem')
    list_editable = ('ordem', 'ativo')
    list_filter = ('ativo', 'prioridade_padrao')
    search_fields = ('nome',)


class OpcaoTriagemInline(admin.TabularInline):
    model = OpcaoTriagem
    fk_name = 'pergunta'
    extra = 2
    fields = ('ordem', 'label', 'icone', 'proxima_pergunta', 'categoria', 'prioridade')
    autocomplete_fields = ('proxima_pergunta', 'categoria')


@admin.register(PerguntaTriagem)
class PerguntaTriagemAdmin(admin.ModelAdmin):
    list_display = ('texto', 'is_raiz', 'ativo', 'ordem')
    list_editable = ('is_raiz', 'ativo', 'ordem')
    list_filter = ('is_raiz', 'ativo')
    search_fields = ('texto',)
    inlines = [OpcaoTriagemInline]


class ChamadoEtapaInline(admin.TabularInline):
    model = ChamadoEtapa
    extra = 0
    readonly_fields = ('tipo', 'autor', 'descricao', 'created_at')
    can_delete = False


@admin.register(Chamado)
class ChamadoAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'titulo', 'categoria', 'prioridade', 'status', 'solicitante', 'responsavel', 'created_at')
    list_filter = ('status', 'prioridade', 'categoria')
    search_fields = ('codigo', 'titulo', 'descricao')
    readonly_fields = ('codigo', 'respostas_triagem', 'created_at', 'updated_at', 'iniciado_em', 'resolvido_em')
    date_hierarchy = 'created_at'
    inlines = [ChamadoEtapaInline]


@admin.register(ChamadoAnexo)
class ChamadoAnexoAdmin(admin.ModelAdmin):
    list_display = ('nome_original', 'chamado', 'enviado_por', 'created_at')
