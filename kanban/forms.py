from django import forms
from core.models import CustomUser, Department
from .models import Board, Column, Card, CardComment, SubTask


class BoardForm(forms.ModelForm):
    class Meta:
        model = Board
        fields = ('name', 'department', 'is_cross_department', 'members')
        widgets = {
            'members': forms.SelectMultiple(attrs={'class': 'form-input'}),
            'name': forms.TextInput(attrs={'class': 'form-input'}),
            'department': forms.Select(attrs={'class': 'form-input'}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['members'].queryset = CustomUser.objects.filter(is_active=True)
        if user and not user.can_see_all:
            self.fields['department'].queryset = Department.objects.filter(pk=user.department_id)


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
        fields = ('column', 'title', 'description', 'assignee', 'due_date', 'priority', 'tags')
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-input'}),
            'description': forms.Textarea(attrs={'rows': 3, 'class': 'form-input'}),
            'assignee': forms.Select(attrs={'class': 'form-input'}),
            'column': forms.Select(attrs={'class': 'form-input'}),
            'due_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-input'}),
            'priority': forms.Select(attrs={'class': 'form-input'}),
            'tags': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'ex: bug, melhoria, urgente'}),
        }

    def __init__(self, *args, board=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['due_date'].required = False
        self.fields['assignee'].required = False
        self.fields['assignee'].empty_label = 'Sem responsável'
        self.fields['tags'].required = False
        self.fields['description'].required = False
        if board:
            self.fields['column'].queryset = Column.objects.filter(board=board)
            if board.is_global or board.is_cross_department:
                # Global/cross-dept boards: todos os usuários ativos
                self.fields['assignee'].queryset = CustomUser.objects.filter(
                    is_active=True, is_approved=True
                ).order_by('first_name', 'last_name')
            elif board.department:
                # Board de departamento: membros do departamento
                qs = CustomUser.objects.filter(
                    is_active=True, is_approved=True, departments=board.department
                ).order_by('first_name', 'last_name')
                if not qs.exists():
                    qs = CustomUser.objects.filter(is_active=True, is_approved=True)
                self.fields['assignee'].queryset = qs
            else:
                members = board.members.filter(is_active=True)
                self.fields['assignee'].queryset = members if members.exists() else CustomUser.objects.filter(is_active=True)


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
        fields = ('title', 'assignee', 'target_department')
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Descreva a sub-tarefa...'}),
            'assignee': forms.Select(attrs={'class': 'form-input'}),
            'target_department': forms.Select(attrs={'class': 'form-input'}),
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
