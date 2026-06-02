from django import forms
from .models import Consulta, Doctor


class ConsultaForm(forms.ModelForm):
    class Meta:
        model = Consulta
        fields = ['doctor', 'patient_name', 'patient_cpf', 'patient_phone',
                  'date', 'time', 'duration_minutes', 'notes']
        widgets = {
            'doctor':           forms.Select(attrs={'class': 'form-input'}),
            'patient_name':     forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Nome completo'}),
            'patient_cpf':      forms.TextInput(attrs={'class': 'form-input', 'placeholder': '000.000.000-00'}),
            'patient_phone':    forms.TextInput(attrs={'class': 'form-input', 'placeholder': '(11) 99999-9999'}),
            'date':             forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
            'time':             forms.TimeInput(attrs={'class': 'form-input', 'type': 'time'}),
            'duration_minutes': forms.NumberInput(attrs={'class': 'form-input', 'min': 10, 'max': 120, 'step': 10}),
            'notes':            forms.Textarea(attrs={'class': 'form-input', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['doctor'].queryset = Doctor.objects.filter(active=True)
        self.fields['patient_cpf'].required = False
        self.fields['patient_phone'].required = False
        self.fields['notes'].required = False


class RescheduleForm(forms.Form):
    doctor = forms.ModelChoiceField(
        queryset=Doctor.objects.filter(active=True),
        label='Médico',
        widget=forms.Select(attrs={'class': 'form-input'}),
    )
    date = forms.DateField(
        label='Nova data',
        widget=forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
    )
    time = forms.TimeField(
        label='Novo horário',
        widget=forms.TimeInput(attrs={'class': 'form-input', 'type': 'time'}),
    )
    notes = forms.CharField(
        label='Observações',
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-input', 'rows': 2}),
    )


class DoctorForm(forms.ModelForm):
    class Meta:
        model = Doctor
        fields = ['name', 'room', 'color', 'user', 'active', 'order']
        widgets = {
            'name':  forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Dr. Almeida'}),
            'room':  forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Sala 1'}),
            'color': forms.TextInput(attrs={'class': 'form-input', 'type': 'color'}),
            'user':  forms.Select(attrs={'class': 'form-input'}),
            'order': forms.NumberInput(attrs={'class': 'form-input', 'min': 0}),
        }
