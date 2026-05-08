from django import forms
from core.models import CustomUser


class MessageForm(forms.Form):
    content = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 1, 'placeholder': 'Digite sua mensagem...', 'class': 'msg-input'}),
        max_length=4000,
    )


class NewConversationForm(forms.Form):
    participants = forms.ModelMultipleChoiceField(
        queryset=CustomUser.objects.none(),
        label='Participantes',
        widget=forms.SelectMultiple(attrs={'class': 'form-input'}),
    )
    is_group = forms.BooleanField(required=False, label='Conversa em grupo')
    name = forms.CharField(max_length=100, required=False, label='Nome do grupo', widget=forms.TextInput(attrs={'class': 'form-input'}))

    def __init__(self, *args, current_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if current_user:
            self.fields['participants'].queryset = CustomUser.objects.filter(is_active=True).exclude(pk=current_user.pk)
