from django import forms

from core.validators import validate_file_extension, validate_file_size

from .models import AtividadeDiretoria, Reembolso


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    """Campo de upload que aceita vários arquivos de uma vez."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('widget', MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_clean = super().clean
        if not isinstance(data, (list, tuple)):
            data = [data] if data else []
        if not data:
            # Nenhum arquivo enviado: dispara a validação de "obrigatório".
            single_clean(None, initial)
            return []
        return [single_clean(d, initial) for d in data]


class ReembolsoForm(forms.ModelForm):
    anexos = MultipleFileField(
        label='Anexos',
        validators=[validate_file_extension, validate_file_size],
        widget=MultipleFileInput(attrs={'class': 'hidden', 'multiple': True}),
        error_messages={'required': 'Anexe pelo menos um arquivo (ex.: comprovante).'},
    )

    class Meta:
        model = Reembolso
        fields = ('titulo', 'descricao', 'valor')
        widgets = {
            'titulo': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Ex.: Reembolso de viagem'}),
            'descricao': forms.Textarea(attrs={'rows': 3, 'class': 'form-input', 'placeholder': 'Detalhe o que está sendo reembolsado...'}),
            'valor': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.01', 'min': '0', 'placeholder': '0,00'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['descricao'].required = False


class AtividadeDiretoriaForm(forms.ModelForm):
    class Meta:
        model = AtividadeDiretoria
        fields = ('data_atividade', 'titulo', 'descricao', 'horas', 'comprovante')
        widgets = {
            'data_atividade': forms.DateInput(attrs={'type': 'date', 'class': 'form-input'}),
            'titulo': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Ex.: Passeata na Av. Paulista'}),
            'descricao': forms.Textarea(attrs={'rows': 3, 'class': 'form-input', 'placeholder': 'O que você fez, onde e por quanto tempo...'}),
            'horas': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.5', 'min': '0', 'placeholder': 'Ex.: 6'}),
            'comprovante': forms.FileInput(attrs={'class': 'form-input text-sm'}),
        }

    def clean_horas(self):
        horas = self.cleaned_data.get('horas')
        if horas is not None and horas <= 0:
            raise forms.ValidationError('Informe um número de horas maior que zero.')
        return horas
