from django import forms

from .models import AtividadeDiretoria, Reembolso


class ReembolsoForm(forms.ModelForm):
    class Meta:
        model = Reembolso
        fields = ('titulo', 'descricao', 'valor', 'papel_assinado', 'comprovante')
        widgets = {
            'titulo': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Ex.: Reembolso de viagem'}),
            'descricao': forms.Textarea(attrs={'rows': 3, 'class': 'form-input', 'placeholder': 'Detalhe o que está sendo reembolsado...'}),
            'valor': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.01', 'min': '0', 'placeholder': '0,00'}),
            'papel_assinado': forms.FileInput(attrs={'class': 'form-input text-sm'}),
            'comprovante': forms.FileInput(attrs={'class': 'form-input text-sm'}),
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
