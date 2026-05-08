from django.conf import settings
from django.db import models
from django.utils import timezone


class Board(models.Model):
    name = models.CharField('Nome', max_length=100)
    department = models.ForeignKey(
        'core.Department', on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name='Departamento', related_name='boards'
    )
    is_cross_department = models.BooleanField('Entre departamentos', default=False)
    is_global = models.BooleanField('Board Geral', default=False)
    is_auto = models.BooleanField('Criado automaticamente', default=False)
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL, verbose_name='Membros', related_name='kanban_boards', blank=True
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name='created_boards', verbose_name='Criado por'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Quadro'
        verbose_name_plural = 'Quadros'
        ordering = ['name']

    def __str__(self):
        return self.name

    def can_access(self, user):
        if user.can_see_all:
            return True
        if self.is_global:
            return True
        if self.is_cross_department:
            return self.members.filter(pk=user.pk).exists()
        return self.department == user.department or self.members.filter(pk=user.pk).exists()


class Column(models.Model):
    board = models.ForeignKey(Board, on_delete=models.CASCADE, related_name='columns', verbose_name='Quadro')
    name = models.CharField('Nome', max_length=80)
    order = models.PositiveSmallIntegerField('Ordem', default=0)
    color = models.CharField('Cor', max_length=7, default='#64748b')
    wip_limit = models.PositiveSmallIntegerField('Limite WIP', default=0, help_text='0 = sem limite')

    class Meta:
        verbose_name = 'Coluna'
        verbose_name_plural = 'Colunas'
        ordering = ['order']

    def __str__(self):
        return f'{self.board} / {self.name}'


class Card(models.Model):
    class Priority(models.TextChoices):
        LOW = 'LOW', 'Baixa'
        MEDIUM = 'MEDIUM', 'Média'
        HIGH = 'HIGH', 'Alta'
        URGENT = 'URGENT', 'Urgente'

    PRIORITY_COLORS = {
        'LOW': '#22c55e',
        'MEDIUM': '#f59e0b',
        'HIGH': '#ef4444',
        'URGENT': '#7c3aed',
    }

    column = models.ForeignKey(Column, on_delete=models.CASCADE, related_name='cards', verbose_name='Coluna')
    title = models.CharField('Título', max_length=200)
    description = models.TextField('Descrição', blank=True)
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='assigned_cards', verbose_name='Responsável'
    )
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name='created_cards', verbose_name='Criado por'
    )
    due_date = models.DateField('Vencimento', null=True, blank=True)
    priority = models.CharField('Prioridade', max_length=10, choices=Priority.choices, default=Priority.MEDIUM)
    tags = models.CharField('Tags', max_length=200, blank=True, help_text='Separadas por vírgula')
    order = models.PositiveIntegerField('Ordem', default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Card'
        verbose_name_plural = 'Cards'
        ordering = ['order', 'created_at']

    def __str__(self):
        return self.title

    @property
    def priority_color(self):
        return self.PRIORITY_COLORS.get(self.priority, '#64748b')

    @property
    def tags_list(self):
        return [t.strip() for t in self.tags.split(',') if t.strip()]

    @property
    def is_overdue(self):
        if self.due_date:
            from django.utils.timezone import now
            return self.due_date < now().date()
        return False


class SubTask(models.Model):
    card = models.ForeignKey(Card, on_delete=models.CASCADE, related_name='subtasks', verbose_name='Card')
    title = models.CharField('Título', max_length=200)
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='assigned_subtasks', verbose_name='Responsável'
    )
    target_department = models.ForeignKey(
        'core.Department', on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name='Área responsável'
    )
    is_done = models.BooleanField('Concluída', default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name='created_subtasks', verbose_name='Criado por'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Sub-tarefa'
        verbose_name_plural = 'Sub-tarefas'
        ordering = ['created_at']

    def __str__(self):
        return self.title


class CardComment(models.Model):
    card = models.ForeignKey(Card, on_delete=models.CASCADE, related_name='comments', verbose_name='Card')
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='card_comments', verbose_name='Autor'
    )
    content = models.TextField('Comentário')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Comentário'
        verbose_name_plural = 'Comentários'
        ordering = ['created_at']

    def __str__(self):
        return f'{self.author} em {self.card}'


class CardActivity(models.Model):
    card = models.ForeignKey(Card, on_delete=models.CASCADE, related_name='activities', verbose_name='Card')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name='card_activities', verbose_name='Usuário'
    )
    action = models.CharField('Ação', max_length=200)
    timestamp = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = 'Atividade do Card'
        verbose_name_plural = 'Atividades do Card'
        ordering = ['-timestamp']

    def __str__(self):
        return f'{self.card} - {self.action}'
