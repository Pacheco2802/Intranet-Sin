from django.contrib import admin
from .models import Board, BoardFolder, Column, Card, CardComment, CardActivity, RecurringTask, PastaDocumento, PastaPost


@admin.register(PastaDocumento)
class PastaDocumentoAdmin(admin.ModelAdmin):
    list_display = ('nome_original', 'folder', 'board', 'enviado_por', 'created_at')
    search_fields = ('nome_original', 'descricao')


@admin.register(PastaPost)
class PastaPostAdmin(admin.ModelAdmin):
    list_display = ('author', 'folder', 'board', 'created_at')
    search_fields = ('content',)


class ColumnInline(admin.TabularInline):
    model = Column
    extra = 0


@admin.register(BoardFolder)
class BoardFolderAdmin(admin.ModelAdmin):
    list_display = ('name', 'department', 'order', 'created_by', 'created_at')
    list_filter = ('department',)
    search_fields = ('name',)


@admin.register(Board)
class BoardAdmin(admin.ModelAdmin):
    list_display = ('name', 'department', 'folder', 'is_cross_department', 'status', 'created_by', 'created_at')
    list_filter = ('department', 'folder', 'status', 'is_cross_department')
    inlines = [ColumnInline]
    filter_horizontal = ('members', 'member_departments')


@admin.register(Card)
class CardAdmin(admin.ModelAdmin):
    list_display = ('title', 'column', 'assignee', 'priority', 'due_date', 'created_at')
    list_filter = ('priority', 'column__board')
    search_fields = ('title', 'description')


@admin.register(RecurringTask)
class RecurringTaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'board', 'frequency', 'active', 'last_generated', 'created_by')
    list_filter  = ('frequency', 'active', 'board')
    search_fields = ('title',)
