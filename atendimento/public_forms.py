"""Formulários das rotas públicas de triagem (QR do slip / totem)."""
import re

from django import forms
from django.core.exceptions import ValidationError

from .forms import _validate_cpf
from .models import TriagemPublica

# Aceita "T12", "t 12", "T-12"; fila J mantida para registros históricos
SENHA_RE = re.compile(r'^([PTAMDJ])\s*-?\s*(\d{1,4})$', re.IGNORECASE)

_INPUT = 'w-full border border-gray-200 rounded-lg px-3 py-3 text-base bg-gray-50 focus:bg-white focus:outline-none transition-all'


class TriagemPublicaForm(forms.Form):
    """Conteúdo da triagem — usado na rota do token (QR do slip)."""

    motivo = forms.ChoiceField(
        label='Qual o motivo da sua visita?',
        choices=[('', 'Selecione o motivo...')] + list(TriagemPublica.Motivo.choices),
        widget=forms.Select(attrs={'class': _INPUT}),
    )
    descricao = forms.CharField(
        label='Conte o seu caso',
        widget=forms.Textarea(attrs={
            'rows': 5, 'class': _INPUT,
            'placeholder': 'Descreva com suas palavras o que aconteceu e o que você precisa...',
        }),
    )
    nome = forms.CharField(
        label='Seu nome completo', required=False, max_length=200,
        widget=forms.TextInput(attrs={'class': _INPUT, 'autocomplete': 'name'}),
    )
    telefone = forms.CharField(
        label='Telefone para contato', required=False, max_length=20,
        widget=forms.TextInput(attrs={
            'class': _INPUT, 'placeholder': '(00) 00000-0000',
            'x-mask': '(99) 99999-9999', 'inputmode': 'tel',
        }),
    )
    email = forms.EmailField(
        label='E-mail', required=False,
        widget=forms.EmailInput(attrs={'class': _INPUT, 'inputmode': 'email'}),
    )
    cargo = forms.CharField(
        label='Cargo/Função', required=False, max_length=120,
        widget=forms.TextInput(attrs={'class': _INPUT, 'placeholder': 'Ex.: Técnico de Enfermagem'}),
    )
    empregador = forms.CharField(
        label='Onde trabalha (empregador)', required=False, max_length=200,
        widget=forms.TextInput(attrs={'class': _INPUT, 'placeholder': 'Ex.: Hospital São Camilo'}),
    )
    lgpd_consent = forms.BooleanField(
        label='Li e concordo com o tratamento dos meus dados',
        widget=forms.CheckboxInput(attrs={'class': 'w-5 h-5 rounded'}),
    )
    # Anti-spam: honeypot (deve vir vazio) + timestamp assinado (tempo mínimo)
    website = forms.CharField(required=False, widget=forms.HiddenInput())
    ts = forms.CharField(required=False, widget=forms.HiddenInput())


class TriagemEntradaForm(TriagemPublicaForm):
    """Formulário do totem / fallback — identificação + conteúdo numa página só."""

    modo = forms.ChoiceField(
        choices=[('codigo', 'codigo'), ('senha', 'senha')],
        initial='codigo', required=False, widget=forms.HiddenInput(),
    )
    codigo = forms.CharField(
        label='Código do seu papel', required=False, max_length=10,
        widget=forms.TextInput(attrs={
            'class': _INPUT + ' uppercase tracking-[0.5em] text-center text-2xl font-bold',
            'placeholder': '••••••',
            'autocomplete': 'off', 'autocapitalize': 'characters',
        }),
    )
    senha = forms.CharField(
        label='Número da sua senha', required=False, max_length=10,
        widget=forms.TextInput(attrs={
            'class': _INPUT + ' uppercase text-center text-xl font-bold',
            'placeholder': 'Ex.: T12', 'autocomplete': 'off', 'autocapitalize': 'characters',
        }),
    )
    cpf = forms.CharField(
        label='Seu CPF', required=False, max_length=14,
        widget=forms.TextInput(attrs={
            'class': _INPUT + ' text-center',
            'placeholder': '000.000.000-00', 'x-mask': '999.999.999-99', 'inputmode': 'numeric',
        }),
    )

    def clean(self):
        data = super().clean()
        modo = data.get('modo') or 'codigo'
        if modo == 'codigo':
            codigo = (data.get('codigo') or '').strip().upper().replace(' ', '')
            if len(codigo) != 6 or not codigo.isalnum():
                self.add_error('codigo', 'Digite o código de 6 letras/números do seu papel.')
            data['codigo'] = codigo
        else:
            senha = (data.get('senha') or '').strip().upper()
            m = SENHA_RE.match(senha)
            if not m:
                self.add_error('senha', 'Digite a senha como aparece no papel. Ex.: T12')
            else:
                data['senha_fila'] = m.group(1).upper()
                data['senha_numero'] = str(int(m.group(2)))
            cpf = data.get('cpf') or ''
            if not _validate_cpf(cpf):
                self.add_error('cpf', 'CPF inválido. Verifique os dígitos informados.')
            else:
                digits = re.sub(r'\D', '', cpf)
                data['cpf'] = f'{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}'
        return data
