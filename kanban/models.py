from django.conf import settings
from django.db import models
from django.utils import timezone
from core.validators import validate_file_extension, validate_file_size


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
        return self.members.filter(pk=user.pk).exists() or user.departments.filter(pk=self.department_id).exists()


class Column(models.Model):
    class ColumnType(models.TextChoices):
        A_FAZER = 'a_fazer', 'A Fazer'
        EM_ANDAMENTO = 'em_andamento', 'Em Andamento'
        STATUS_FINAL = 'status_final', 'Status Final'

    board = models.ForeignKey(Board, on_delete=models.CASCADE, related_name='columns', verbose_name='Quadro')
    name = models.CharField('Nome', max_length=80)
    column_type = models.CharField(
        'Tipo', max_length=20, choices=ColumnType.choices,
        default=ColumnType.A_FAZER,
    )
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
    source_subtask = models.ForeignKey(
        'SubTask', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='kanban_cards', verbose_name='Subtarefa de origem',
    )
    source_atendimento_id = models.PositiveIntegerField(
        'ID do atendimento de origem', null=True, blank=True
    )
    final_status = models.CharField('Status final', max_length=20, blank=True, default='',
        choices=[
            ('concluido', 'Concluído'),
            ('nao_concluido', 'Não concluído'),
            ('cancelado', 'Cancelado'),
        ]
    )
    final_notes = models.TextField('Observações de conclusão', blank=True)
    completed_at = models.DateTimeField('Concluído em', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Card'
        verbose_name_plural = 'Cards'
        ordering = ['order', '-created_at']

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
        if self.due_date and not self.final_status:
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
    due_date = models.DateField('Vencimento', null=True, blank=True)
    is_done = models.BooleanField('Concluída', default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name='created_subtasks', verbose_name='Criado por'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def is_overdue(self):
        if self.due_date and not self.is_done:
            from django.utils.timezone import now
            return self.due_date < now().date()
        return False

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


class CardAnexo(models.Model):
    card = models.ForeignKey(Card, on_delete=models.CASCADE, related_name='anexos', verbose_name='Card')
    arquivo = models.FileField(
        'Arquivo', upload_to='cards/%Y/%m/',
        validators=[validate_file_extension, validate_file_size],
    )
    nome_original = models.CharField('Nome do arquivo', max_length=255)
    enviado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, verbose_name='Enviado por'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Anexo de Card'
        verbose_name_plural = 'Anexos de Card'
        ordering = ['created_at']

    def __str__(self):
        return self.nome_original


class SubTaskAnexo(models.Model):
    subtask = models.ForeignKey(SubTask, on_delete=models.CASCADE, related_name='anexos', verbose_name='Sub-tarefa')
    arquivo = models.FileField(
        'Arquivo', upload_to='subtarefas/%Y/%m/',
        validators=[validate_file_extension, validate_file_size],
    )
    nome_original = models.CharField('Nome do arquivo', max_length=255)
    enviado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, verbose_name='Enviado por'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Anexo de Sub-tarefa'
        verbose_name_plural = 'Anexos de Sub-tarefas'
        ordering = ['created_at']

    def __str__(self):
        return self.nome_original


class RecurringTask(models.Model):
    class Frequency(models.TextChoices):
        DIARIO     = 'diario',     'Diário'
        SEMANAL    = 'semanal',    'Semanal'
        QUINZENAL  = 'quinzenal',  'Quinzenal'
        MENSAL     = 'mensal',     'Mensal'

    WEEKDAY_CHOICES = [
        (0, 'Segunda-feira'), (1, 'Terça-feira'), (2, 'Quarta-feira'),
        (3, 'Quinta-feira'),  (4, 'Sexta-feira'),  (5, 'Sábado'), (6, 'Domingo'),
    ]

    board        = models.ForeignKey(Board, on_delete=models.CASCADE, related_name='recurring_tasks', verbose_name='Quadro')
    column       = models.ForeignKey(Column, on_delete=models.CASCADE, related_name='recurring_tasks', verbose_name='Coluna inicial')
    title        = models.CharField('Título', max_length=200)
    description  = models.TextField('Descrição', blank=True)
    assignee     = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='recurring_tasks', verbose_name='Responsável',
    )
    priority     = models.CharField('Prioridade', max_length=10, choices=Card.Priority.choices, default=Card.Priority.MEDIUM)
    tags         = models.CharField('Tags', max_length=200, blank=True)
    frequency    = models.CharField('Frequência', max_length=15, choices=Frequency.choices)
    day_of_week  = models.SmallIntegerField('Dia da semana', null=True, blank=True, choices=WEEKDAY_CHOICES,
                                             help_text='Usado para frequência semanal e quinzenal')
    day_of_month = models.SmallIntegerField('Dia do mês', null=True, blank=True,
                                             help_text='Usado para frequência mensal (1–28)')
    due_days_ahead = models.SmallIntegerField('Prazo (dias após criação)', default=0,
                                               help_text='0 = sem prazo automático')
    active         = models.BooleanField('Ativa', default=True)
    created_by     = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name='created_recurring_tasks', verbose_name='Criado por',
    )
    last_generated = models.DateField('Última geração', null=True, blank=True)
    created_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Tarefa Recorrente'
        verbose_name_plural = 'Tarefas Recorrentes'
        ordering = ['board', 'title']

    def __str__(self):
        return f'{self.title} ({self.get_frequency_display()})'

    def should_generate_today(self, today) -> bool:
        from datetime import timedelta
        lg = self.last_generated
        f  = self.frequency
        if f == self.Frequency.DIARIO:
            return lg is None or lg < today
        if f == self.Frequency.SEMANAL:
            return today.weekday() == self.day_of_week and (lg is None or (today - lg).days >= 7)
        if f == self.Frequency.QUINZENAL:
            return today.weekday() == self.day_of_week and (lg is None or (today - lg).days >= 14)
        if f == self.Frequency.MENSAL:
            return today.day == self.day_of_month and (lg is None or lg.month != today.month or lg.year != today.year)
        return False

    def generate_card(self, today):
        from datetime import timedelta
        suffix = f' — {today.strftime("%d/%m/%Y")}' if self.frequency == self.Frequency.DIARIO else ''
        tags = ','.join(filter(None, [t.strip() for t in self.tags.split(',') if t.strip()] + ['recorrente']))
        last = Card.objects.filter(column=self.column).order_by('-order').first()
        due  = today + timedelta(days=self.due_days_ahead) if self.due_days_ahead else None
        card = Card.objects.create(
            column      = self.column,
            title       = self.title + suffix,
            description = self.description,
            assignee    = self.assignee,
            priority    = self.priority,
            tags        = tags,
            due_date    = due,
            order       = (last.order + 1) if last else 0,
            creator     = self.created_by,
        )
        self.last_generated = today
        self.save(update_fields=['last_generated'])
        return card


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
