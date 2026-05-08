from django import forms
from .models import Comunicado


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
