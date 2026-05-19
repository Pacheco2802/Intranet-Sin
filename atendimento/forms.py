import re
from django import forms
from django.core.exceptions import ValidationError
from core.models import Department, CustomUser
from core.validators import validate_file_extension, validate_file_size
from .models import Atendimento, AtendimentoEtapa, AtendimentoAnexo


def _validate_cpf(cpf: str) -> bool:
    digits = re.sub(r'\D', '', cpf)
    if len(digits) != 11 or len(set(digits)) == 1:
        return False
    for pos in range(9, 11):
        total = sum(int(d) * (pos + 1 - i) for i, d in enumerate(digits[:pos]))
        expected = (total * 10 % 11) % 10
        if expected != int(digits[pos]):
            return False
    return True


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

    def clean_cpf(self):
        cpf = self.cleaned_data.get('cpf', '')
        if not _validate_cpf(cpf):
            raise ValidationError('CPF inválido. Verifique os dígitos informados.')
        digits = re.sub(r'\D', '', cpf)
        return f'{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}'


class EtapaNotaForm(forms.Form):
    descricao = forms.CharField(
        label='Anotação',
        widget=forms.Textarea(attrs={'rows': 3, 'class': 'form-input', 'placeholder': 'Descreva o que foi discutido, acordado...'})
    )
    arquivo = forms.FileField(
        label='Anexar arquivo (opcional)',
        required=False,
        widget=forms.FileInput(attrs={'class': 'form-input'}),
        validators=[validate_file_extension, validate_file_size],
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
        widget=forms.FileInput(attrs={'class': 'form-input'}),
        validators=[validate_file_extension, validate_file_size],
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
