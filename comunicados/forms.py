import re
from django import forms
from .models import Comunicado

_DANGEROUS_TAGS = re.compile(
    r'<\s*(script|iframe|object|embed|form|input|button|link|meta|base|style)[^>]*>.*?</\s*\1\s*>|'
    r'<\s*(script|iframe|object|embed|form|input|button|link|meta|base|style)[^>]*/?>',
    re.IGNORECASE | re.DOTALL,
)
_EVENT_ATTRS = re.compile(r'\s+on\w+\s*=\s*["\'][^"\']*["\']', re.IGNORECASE)

_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'webp'}


class ComunicadoForm(forms.ModelForm):
    class Meta:
        model = Comunicado
        fields = ['title', 'content', 'cover_image', 'is_pinned', 'expires_at', 'departments']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-input text-lg font-semibold',
                'placeholder': 'Título do comunicado...',
            }),
            'content': forms.Textarea(attrs={
                'rows': 12,
                'class': 'form-input font-normal leading-relaxed',
                'placeholder': 'Escreva o conteúdo do comunicado aqui...',
                'id': 'id_content',
            }),
            'cover_image': forms.FileInput(attrs={'class': 'hidden', 'id': 'id_cover_image', 'accept': 'image/*'}),
            'is_pinned': forms.CheckboxInput(attrs={'class': 'w-4 h-4 text-accent rounded'}),
            'expires_at': forms.DateTimeInput(
                attrs={'type': 'datetime-local', 'class': 'form-input'},
                format='%Y-%m-%dT%H:%M',
            ),
            'departments': forms.CheckboxSelectMultiple(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['cover_image'].required = False
        self.fields['is_pinned'].required = False
        self.fields['expires_at'].required = False
        self.fields['departments'].required = False
        if self.instance and self.instance.expires_at:
            self.initial['expires_at'] = self.instance.expires_at.strftime('%Y-%m-%dT%H:%M')

    def clean_content(self):
        content = self.cleaned_data.get('content', '')
        content = _DANGEROUS_TAGS.sub('', content)
        content = _EVENT_ATTRS.sub('', content)
        return content

    def clean_cover_image(self):
        img = self.cleaned_data.get('cover_image')
        if img and hasattr(img, 'name'):
            ext = img.name.rsplit('.', 1)[-1].lower() if '.' in img.name else ''
            if ext not in _IMAGE_EXTENSIONS:
                raise forms.ValidationError('Apenas imagens são permitidas (JPG, PNG, GIF, WEBP).')
            if img.size > 5 * 1024 * 1024:
                raise forms.ValidationError('A imagem não pode exceder 5 MB.')
        return img
