from django import forms
from core.models import CustomUser
from .models import Event


class EventForm(forms.ModelForm):
    participants = forms.ModelMultipleChoiceField(
        label='Participantes',
        queryset=CustomUser.objects.none(),
        widget=forms.SelectMultiple(attrs={'class': 'form-input', 'size': '6'}),
        required=False,
    )

    class Meta:
        model = Event
        fields = ('title', 'description', 'location', 'start_datetime', 'end_datetime')
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-input'}),
            'description': forms.Textarea(attrs={'rows': 3, 'class': 'form-input'}),
            'location': forms.TextInput(attrs={'class': 'form-input'}),
            'start_datetime': forms.DateTimeInput(
                attrs={'type': 'datetime-local', 'class': 'form-input'},
                format='%Y-%m-%dT%H:%M',
            ),
            'end_datetime': forms.DateTimeInput(
                attrs={'type': 'datetime-local', 'class': 'form-input'},
                format='%Y-%m-%dT%H:%M',
            ),
        }

    def __init__(self, *args, current_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['end_datetime'].required = False
        qs = CustomUser.objects.filter(is_active=True, is_approved=True).order_by('first_name', 'last_name')
        if current_user:
            qs = qs.exclude(pk=current_user.pk)
        self.fields['participants'].queryset = qs
        # Pre-populate on edit
        if self.instance.pk:
            self.fields['participants'].initial = self.instance.participants.values_list('user', flat=True)
