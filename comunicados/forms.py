import re
from django import forms
from .models import Comunicado

_DANGEROUS_TAGS = re.compile(
    r'<\s*(script|iframe|object|embed|form|input|button|link|meta|base|style)[^>]*>.*?</\s*\1\s*>|'
    r'<\s*(script|iframe|object|embed|form|input|button|link|meta|base|style)[^>]*/?>',
    re.IGNORECASE | re.DOTALL,
)
_EVENT_ATTRS = re.compile(r'\s+on\w+\s*=\s*["\'][^"\']*["\']', re.IGNORECASE)


class ComunicadoForm(forms.ModelForm):
    class Meta:
        model = Comunicado
        fields = ['title', 'content', 'is_pinned', 'is_published', 'published_at', 'expires_at', 'departments']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-input'}),
            'content': forms.Textarea(attrs={'rows': 8, 'class': 'form-input'}),
            'published_at': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-input'}),
            'expires_at': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-input'}),
            'departments': forms.CheckboxSelectMultiple(),
        }

    def clean_content(self):
        content = self.cleaned_data.get('content', '')
        content = _DANGEROUS_TAGS.sub('', content)
        content = _EVENT_ATTRS.sub('', content)
        return content
