from django.contrib import admin
from .models import Board, Column, Card, CardComment, CardActivity, RecurringTask


class ColumnInline(admin.TabularInline):
    model = Column
    extra = 0


@admin.register(Board)
class BoardAdmin(admin.ModelAdmin):
    list_display = ('name', 'department', 'is_cross_department', 'created_by', 'created_at')
    inlines = [ColumnInline]
    filter_horizontal = ('members',)


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
