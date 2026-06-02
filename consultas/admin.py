from django.contrib import admin
from .models import ASO, Atendimento, Consulta, ConsultaDocumento, Doctor


@admin.register(Doctor)
class DoctorAdmin(admin.ModelAdmin):
    list_display = ('name', 'room', 'active', 'order')
    list_editable = ('order', 'active')


@admin.register(Consulta)
class ConsultaAdmin(admin.ModelAdmin):
    list_display  = ('patient_name', 'doctor', 'date', 'time', 'status', 'created_by')
    list_filter   = ('status', 'doctor', 'date')
    search_fields = ('patient_name', 'patient_cpf')
    date_hierarchy = 'date'


@admin.register(Atendimento)
class AtendimentoAdmin(admin.ModelAdmin):
    list_display  = ('consulta', 'finalizado', 'finalizado_em', 'finalizado_por')
    list_filter   = ('finalizado',)
    raw_id_fields = ('consulta',)


@admin.register(ConsultaDocumento)
class ConsultaDocumentoAdmin(admin.ModelAdmin):
    list_display  = ('titulo', 'tipo', 'consulta', 'enviado_por', 'created_at')
    list_filter   = ('tipo',)
    raw_id_fields = ('consulta',)


@admin.register(ASO)
class ASOAdmin(admin.ModelAdmin):
    list_display  = ('consulta', 'tipo_exame', 'resultado', 'data_emissao', 'created_by')
    list_filter   = ('tipo_exame', 'resultado')
    raw_id_fields = ('consulta',)
