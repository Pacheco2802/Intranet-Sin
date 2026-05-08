from django import forms
from core.models import Department, CustomUser
from .models import Atendimento, AtendimentoEtapa, AtendimentoAnexo


class AtendimentoForm(forms.ModelForm):
    class Meta:
        model = Atendimento
        fields = ('cpf', 'nome_filiado', 'telefone', 'email_filiado', 'assunto', 'descricao')
        widgets = {
            'cpf': forms.TextInput(attrs={
                'class': 'form-input', 'placeholder': '000.000.000-00',
                'x-mask': '999.999.999-99',
            }),
            'nome_filiado': forms.TextInput(attrs={'class': 'form-input'}),
            'telefone': forms.TextInput(attrs={'class': 'form-input', 'placeholder': '(00) 00000-0000'}),
            'email_filiado': forms.EmailInput(attrs={'class': 'form-input'}),
            'assunto': forms.TextInput(attrs={'class': 'form-input'}),
            'descricao': forms.Textarea(attrs={'rows': 4, 'class': 'form-input', 'placeholder': 'Descreva o motivo do atendimento...'}),
        }


class EtapaNotaForm(forms.Form):
    descricao = forms.CharField(
        label='Anotação',
        widget=forms.Textarea(attrs={'rows': 3, 'class': 'form-input', 'placeholder': 'Descreva o que foi discutido, acordado...'})
    )
    arquivo = forms.FileField(
        label='Anexar arquivo (opcional)',
        required=False,
        widget=forms.FileInput(attrs={'class': 'form-input'})
    )


class EncaminharForm(forms.Form):
    para_departamento = forms.ModelChoiceField(
        queryset=Department.objects.all().order_by('name'),
        label='Encaminhar para',
        empty_label='Selecione o departamento',
        widget=forms.Select(attrs={'class': 'form-input'})
    )
    descricao = forms.CharField(
        label='Observações (opcional)',
        required=False,
        widget=forms.Textarea(attrs={'rows': 2, 'class': 'form-input', 'placeholder': 'Instruções para o próximo departamento...'})
    )


class ConcluirForm(forms.Form):
    descricao = forms.CharField(
        label='Resumo da conclusão',
        widget=forms.Textarea(attrs={'rows': 3, 'class': 'form-input', 'placeholder': 'Descreva o resultado final do atendimento...'})
    )
    arquivo = forms.FileField(
        label='Anexar arquivo (opcional)',
        required=False,
        widget=forms.FileInput(attrs={'class': 'form-input'})
    )


class AtendimentoFilterForm(forms.Form):
    cpf = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'CPF do filiado'})
    )
    nome = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Nome do filiado'})
    )
    status = forms.ChoiceField(
        required=False,
        choices=[('', 'Todos os status')] + list(Atendimento.Status.choices),
        widget=forms.Select(attrs={'class': 'form-input'})
    )
    departamento = forms.ModelChoiceField(
        required=False,
        queryset=Department.objects.all().order_by('name'),
        empty_label='Todos os departamentos',
        widget=forms.Select(attrs={'class': 'form-input'})
    )
