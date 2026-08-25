import re

from django import forms
from django.core.exceptions import ValidationError

from atendimento.forms import _validate_cpf
from atendimento.models import _cpf_hash
from core.validators import validate_file_extension, validate_file_size

from .models import Associado, Caso, CasoDocumento


class AssociadoForm(forms.ModelForm):
    # Campos criptografados são TextField no model — declarados aqui para
    # renderizarem como inputs normais
    cpf = forms.CharField(
        label='CPF', max_length=14,
        widget=forms.TextInput(attrs={
            'class': 'form-input', 'placeholder': '000.000.000-00',
            'x-mask': '999.999.999-99',
        }),
    )
    telefone = forms.CharField(
        label='Telefone', required=False, max_length=20,
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': '(00) 00000-0000'}),
    )
    data_nascimento = forms.DateField(
        label='Data de nascimento', required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-input'}),
    )

    class Meta:
        model = Associado
        fields = ('cpf', 'nome', 'telefone', 'email', 'data_nascimento',
                  'cargo', 'empregador', 'observacoes')
        widgets = {
            'nome': forms.TextInput(attrs={'class': 'form-input'}),
            'email': forms.EmailInput(attrs={'class': 'form-input'}),
            'cargo': forms.TextInput(attrs={'class': 'form-input'}),
            'empregador': forms.TextInput(attrs={'class': 'form-input'}),
            'observacoes': forms.Textarea(attrs={'rows': 3, 'class': 'form-input'}),
        }

    def clean_cpf(self):
        cpf = self.cleaned_data.get('cpf', '')
        if not _validate_cpf(cpf):
            raise ValidationError('CPF inválido. Verifique os dígitos informados.')
        digits = re.sub(r'\D', '', cpf)
        formatado = f'{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}'
        h = _cpf_hash(formatado)
        qs = Associado.objects.filter(cpf_hash=h)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError('Já existe uma ficha de associado com este CPF.')
        return formatado


class CasoForm(forms.ModelForm):
    class Meta:
        model = Caso
        fields = ('tipo', 'titulo', 'descricao', 'status',
                  'departamento_responsavel', 'responsavel')
        widgets = {
            'tipo': forms.Select(attrs={'class': 'form-input'}),
            'titulo': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Ex.: Verbas rescisórias — Hospital X'}),
            'descricao': forms.Textarea(attrs={'rows': 4, 'class': 'form-input'}),
            'status': forms.Select(attrs={'class': 'form-input'}),
            'departamento_responsavel': forms.Select(attrs={'class': 'form-input'}),
            'responsavel': forms.Select(attrs={'class': 'form-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from core.models import CustomUser
        self.fields['responsavel'].queryset = CustomUser.objects.filter(
            is_active=True, is_approved=True
        ).order_by('first_name', 'last_name')
        self.fields['responsavel'].required = False
        self.fields['departamento_responsavel'].required = False


class CasoDocumentoForm(forms.Form):
    tipo = forms.ChoiceField(
        label='Tipo', choices=CasoDocumento.Tipo.choices,
        widget=forms.Select(attrs={'class': 'form-input'}),
    )
    arquivo = forms.FileField(
        label='Arquivo',
        widget=forms.FileInput(attrs={'class': 'form-input'}),
        validators=[validate_file_extension, validate_file_size],
    )
