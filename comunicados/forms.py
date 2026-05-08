from django import forms
from .models import Comunicado


class ComunicadoForm(forms.ModelForm):
    publish_now = forms.BooleanField(required=False, label='Publicar agora')

    class Meta:
        model = Comunicado
        fields = ('title', 'content', 'departments', 'is_pinned', 'expires_at')
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-input'}),
            'content': forms.Textarea(attrs={'rows': 8, 'class': 'form-input'}),
            'departments': forms.SelectMultiple(attrs={'class': 'form-input'}),
            'expires_at': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-input'}),
        }
