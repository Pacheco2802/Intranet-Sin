from django.contrib import admin
from .models import Doctor, Consulta


@admin.register(Doctor)
class DoctorAdmin(admin.ModelAdmin):
    list_display = ('name', 'room', 'active', 'order')
    list_editable = ('order', 'active')


@admin.register(Consulta)
class ConsultaAdmin(admin.ModelAdmin):
    list_display = ('patient_name', 'doctor', 'date', 'time', 'status', 'created_by')
    list_filter  = ('status', 'doctor', 'date')
    search_fields = ('patient_name', 'patient_cpf')
    date_hierarchy = 'date'
