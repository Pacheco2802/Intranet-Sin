from django import forms

from core.validators import validate_file_extension, validate_file_size
from .models import Chamado, CategoriaChamado, Prioridade


class ChamadoFinalForm(forms.ModelForm):
    """Passo final do assistente: título + descrição do problema (+ anexo opcional).
    Categoria e prioridade vêm da triagem, não deste formulário."""
    arquivo = forms.FileField(
        label='Anexar arquivo (opcional)',
        required=False,
        widget=forms.FileInput(attrs={'class': 'form-input text-sm'}),
        validators=[validate_file_extension, validate_file_size],
    )

    class Meta:
        model = Chamado
        fields = ('titulo', 'descricao')
        widgets = {
            'titulo': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Resuma o problema em uma frase',
            }),
            'descricao': forms.Textarea(attrs={
                'rows': 4, 'class': 'form-input',
                'placeholder': 'Descreva com detalhes: o que acontece, quando começou, mensagens de erro...',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['titulo'].required = True


class ChamadoManualForm(ChamadoFinalForm):
    """Fallback quando a árvore de triagem ainda não foi configurada: o usuário
    escolhe a categoria manualmente."""
    class Meta(ChamadoFinalForm.Meta):
        fields = ('categoria', 'titulo', 'descricao')
        widgets = dict(
            ChamadoFinalForm.Meta.widgets,
            categoria=forms.Select(attrs={'class': 'form-input'}),
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['categoria'].queryset = CategoriaChamado.objects.filter(ativo=True)
        self.fields['categoria'].required = True
        self.fields['categoria'].empty_label = 'Selecione a categoria'


class ComentarioForm(forms.Form):
    descricao = forms.CharField(
        label='Comentário',
        widget=forms.Textarea(attrs={
            'rows': 3, 'class': 'form-input',
            'placeholder': 'Escreva um comentário ou registre um andamento...',
        }),
    )
    arquivo = forms.FileField(
        label='Anexar arquivo (opcional)',
        required=False,
        widget=forms.FileInput(attrs={'class': 'form-input text-sm'}),
        validators=[validate_file_extension, validate_file_size],
    )


class ChamadoFilterForm(forms.Form):
    q = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Código ou título'}),
    )
    status = forms.ChoiceField(
        required=False,
        choices=[('', 'Todos os status')] + list(Chamado.Status.choices),
        widget=forms.Select(attrs={'class': 'form-input'}),
    )
    categoria = forms.ModelChoiceField(
        required=False,
        queryset=CategoriaChamado.objects.all().order_by('ordem', 'nome'),
        empty_label='Todas as categorias',
        widget=forms.Select(attrs={'class': 'form-input'}),
    )
    prioridade = forms.ChoiceField(
        required=False,
        choices=[('', 'Todas as prioridades')] + list(Prioridade.choices),
        widget=forms.Select(attrs={'class': 'form-input'}),
    )
