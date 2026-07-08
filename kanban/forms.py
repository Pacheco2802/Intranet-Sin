from django import forms
from core.models import CustomUser, Department
from .models import Board, BoardFolder, Column, Card, CardComment, SubTask, RecurringTask


class BoardForm(forms.ModelForm):
    class Meta:
        model = Board
        fields = ('name', 'department', 'folder', 'members')
        widgets = {
            'members': forms.SelectMultiple(attrs={'class': 'form-input'}),
            'name': forms.TextInput(attrs={'class': 'form-input'}),
            'department': forms.Select(attrs={'class': 'form-input'}),
            'folder': forms.Select(attrs={'class': 'form-input'}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['members'].queryset = CustomUser.objects.filter(is_active=True)
        self.fields['department'].required = True
        self.fields['folder'].required = False
        self.fields['folder'].empty_label = 'Sem pasta (Geral)'
        folders = BoardFolder.objects.select_related('department')
        # Escopo = departamentos que o usuário gerencia (mesma regra de
        # pode_gerenciar_pastas): admin TI / presidência veem tudo; os demais,
        # apenas os departamentos que lideram.
        if user and not (user.is_admin_ti or user.is_presidente):
            depts = Department.objects.filter(leaders=user).distinct()
            self.fields['department'].queryset = depts
            folders = folders.filter(department__in=depts)
        self.fields['folder'].queryset = folders

    def clean(self):
        cleaned = super().clean()
        folder = cleaned.get('folder')
        dept = cleaned.get('department')
        if folder and dept and folder.department_id != dept.pk:
            self.add_error('folder', 'A pasta escolhida não pertence ao departamento selecionado.')
        return cleaned


class ProjectForm(forms.ModelForm):
    """Projeto = quadro colaborativo entre áreas (is_cross_department=True)."""
    class Meta:
        model = Board
        fields = ('name', 'member_departments', 'members')
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Ex.: Campanha de vacinação 2026'}),
            # member_departments e members são renderizados como pickers customizados
            # (chips + busca) no template; ver projeto_form.html.
            'member_departments': forms.SelectMultiple(),
            'members': forms.SelectMultiple(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['member_departments'].queryset = Department.objects.order_by('name')
        self.fields['member_departments'].required = False
        self.fields['members'].queryset = CustomUser.objects.filter(is_active=True, is_approved=True)
        self.fields['members'].required = False

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get('member_departments') and not cleaned.get('members'):
            raise forms.ValidationError('Escolha pelo menos uma área ou uma pessoa para participar do projeto.')
        return cleaned


class BoardFolderForm(forms.ModelForm):
    class Meta:
        model = BoardFolder
        fields = ('name', 'description', 'icon', 'color', 'order')
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Ex.: Projetos 2026'}),
            'description': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Opcional'}),
            'icon': forms.TextInput(attrs={'class': 'form-input', 'placeholder': '📁'}),
            'color': forms.TextInput(attrs={'type': 'color', 'class': 'form-input'}),
            'order': forms.NumberInput(attrs={'class': 'form-input', 'min': '0'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in ('description', 'icon', 'color', 'order'):
            self.fields[f].required = False


class ColumnForm(forms.ModelForm):
    class Meta:
        model = Column
        fields = ('name', 'column_type', 'color', 'order', 'wip_limit')
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input'}),
            'column_type': forms.Select(attrs={'class': 'form-input'}),
            'color': forms.TextInput(attrs={'type': 'color', 'class': 'form-input'}),
            'order': forms.NumberInput(attrs={'class': 'form-input', 'min': '0'}),
            'wip_limit': forms.NumberInput(attrs={'class': 'form-input', 'min': '0'}),
        }


class CardForm(forms.ModelForm):
    class Meta:
        model = Card
        fields = ('column', 'title', 'description', 'assignee', 'due_date',
                  'priority', 'tags', 'is_private', 'allowed_users')
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-input'}),
            'description': forms.Textarea(attrs={'rows': 3, 'class': 'form-input'}),
            'assignee': forms.Select(attrs={'class': 'form-input'}),
            'column': forms.Select(attrs={'class': 'form-input'}),
            'due_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-input'}),
            'priority': forms.Select(attrs={'class': 'form-input'}),
            'tags': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'ex: bug, melhoria, urgente'}),
            'is_private': forms.CheckboxInput(attrs={'class': 'hidden'}),
            'allowed_users': forms.SelectMultiple(),
        }

    def __init__(self, *args, board=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['due_date'].required = False
        self.fields['assignee'].required = False
        self.fields['assignee'].empty_label = 'Sem responsável'
        self.fields['tags'].required = False
        self.fields['description'].required = False
        self.fields['is_private'].required = False
        self.fields['allowed_users'].required = False
        if board:
            self.fields['column'].queryset = Column.objects.filter(board=board)
            # Pessoas elegíveis para responsável / acesso a card privado: mesma regra.
            if board.is_global or board.is_cross_department:
                # Global/cross-dept boards: todos os usuários ativos
                elegiveis = CustomUser.objects.filter(
                    is_active=True, is_approved=True
                ).order_by('first_name', 'last_name')
            elif board.department:
                # Board de departamento: membros do departamento
                elegiveis = CustomUser.objects.filter(
                    is_active=True, is_approved=True, departments=board.department
                ).order_by('first_name', 'last_name')
                if not elegiveis.exists():
                    elegiveis = CustomUser.objects.filter(is_active=True, is_approved=True)
            else:
                members = board.members.filter(is_active=True)
                elegiveis = members if members.exists() else CustomUser.objects.filter(is_active=True)
            self.fields['assignee'].queryset = elegiveis
            self.fields['allowed_users'].queryset = elegiveis


class CardCommentForm(forms.ModelForm):
    class Meta:
        model = CardComment
        fields = ('content',)
        widgets = {
            'content': forms.Textarea(attrs={'rows': 2, 'class': 'form-input', 'placeholder': 'Adicionar comentário...'}),
        }


class SubTaskForm(forms.ModelForm):
    class Meta:
        model = SubTask
        fields = ('title', 'assignee', 'target_department', 'due_date')
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Descreva a sub-tarefa...'}),
            'assignee': forms.Select(attrs={'class': 'form-input'}),
            'target_department': forms.Select(attrs={'class': 'form-input'}),
            'due_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['assignee'].queryset = CustomUser.objects.filter(
            is_active=True, is_approved=True
        ).order_by('first_name', 'last_name')
        self.fields['assignee'].empty_label = 'Sem responsável'
        self.fields['assignee'].required = False
        self.fields['target_department'].queryset = Department.objects.all().order_by('name')
        self.fields['target_department'].empty_label = 'Nenhuma área específica'
        self.fields['target_department'].required = False


class RecurringTaskForm(forms.ModelForm):
    class Meta:
        model = RecurringTask
        fields = (
            'board', 'column', 'title', 'description',
            'assignee', 'priority', 'tags',
            'frequency', 'day_of_week', 'day_of_month', 'due_days_ahead', 'active',
        )
        widgets = {
            'board':          forms.Select(attrs={'class': 'form-input', 'id': 'id_rt_board'}),
            'column':         forms.Select(attrs={'class': 'form-input', 'id': 'id_rt_column'}),
            'title':          forms.TextInput(attrs={'class': 'form-input'}),
            'description':    forms.Textarea(attrs={'rows': 2, 'class': 'form-input'}),
            'assignee':       forms.Select(attrs={'class': 'form-input'}),
            'priority':       forms.Select(attrs={'class': 'form-input'}),
            'tags':           forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'ex: reunião, relatório'}),
            'frequency':      forms.Select(attrs={'class': 'form-input', 'id': 'id_rt_frequency'}),
            'day_of_week':    forms.Select(attrs={'class': 'form-input'}),
            'day_of_month':   forms.NumberInput(attrs={'class': 'form-input', 'min': 1, 'max': 28}),
            'due_days_ahead': forms.NumberInput(attrs={'class': 'form-input', 'min': 0}),
            'active':         forms.CheckboxInput(attrs={'class': 'rounded'}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['description'].required  = False
        self.fields['assignee'].required     = False
        self.fields['assignee'].empty_label  = 'Sem responsável'
        self.fields['tags'].required         = False
        self.fields['day_of_week'].required  = False
        self.fields['day_of_month'].required = False
        self.fields['assignee'].queryset = CustomUser.objects.filter(
            is_active=True, is_approved=True
        ).order_by('first_name', 'last_name')
        self.fields['day_of_week'].choices = [('', '— selecione —')] + RecurringTask.WEEKDAY_CHOICES
        # Restringe boards ao que o usuário pode acessar
        if user is not None:
            from django.db.models import Q
            from .models import Board
            if user.can_see_all:
                self.fields['board'].queryset = Board.objects.all()
            else:
                self.fields['board'].queryset = Board.objects.filter(
                    Q(department__in=user.departments.all()) |
                    Q(members=user) |
                    Q(is_global=True)
                ).distinct()

    def clean(self):
        data = super().clean()
        freq = data.get('frequency')
        if freq in ('semanal', 'quinzenal') and data.get('day_of_week') is None:
            self.add_error('day_of_week', 'Informe o dia da semana para esta frequência.')
        if freq == 'mensal' and not data.get('day_of_month'):
            self.add_error('day_of_month', 'Informe o dia do mês para frequência mensal.')
        # Ensure column belongs to board
        board  = data.get('board')
        column = data.get('column')
        if board and column and column.board_id != board.pk:
            self.add_error('column', 'Esta coluna não pertence ao quadro selecionado.')
        return data
