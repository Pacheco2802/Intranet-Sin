from django import forms
from .models import ASO, Atendimento, Consulta, ConsultaDocumento, Doctor


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
        fields = ['name', 'room', 'color', 'user', 'active', 'is_medico', 'order']
        widgets = {
            'name':      forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Dr. Almeida'}),
            'room':      forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Sala 1'}),
            'color':     forms.TextInput(attrs={'class': 'form-input', 'type': 'color'}),
            'user':      forms.Select(attrs={'class': 'form-input'}),
            'is_medico': forms.CheckboxInput(),
            'order':     forms.NumberInput(attrs={'class': 'form-input', 'min': 0}),
        }


class AtendimentoForm(forms.ModelForm):
    class Meta:
        model = Atendimento
        fields = ['pressao_arterial', 'peso', 'altura', 'queixa_principal',
                  'anamnese', 'exame_clinico', 'diagnostico', 'cid', 'conduta']
        widgets = {
            'pressao_arterial':  forms.TextInput(attrs={'class': 'form-input', 'placeholder': '120/80'}),
            'peso':              forms.NumberInput(attrs={'class': 'form-input', 'placeholder': '70.0', 'step': '0.1'}),
            'altura':            forms.NumberInput(attrs={'class': 'form-input', 'placeholder': '1.70', 'step': '0.01'}),
            'queixa_principal':  forms.Textarea(attrs={'class': 'form-input', 'rows': 2}),
            'anamnese':          forms.Textarea(attrs={'class': 'form-input', 'rows': 4}),
            'exame_clinico':     forms.Textarea(attrs={'class': 'form-input', 'rows': 3}),
            'diagnostico':       forms.Textarea(attrs={'class': 'form-input', 'rows': 2}),
            'cid':               forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Z00.0'}),
            'conduta':           forms.Textarea(attrs={'class': 'form-input', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.required = False


class ConsultaDocumentoForm(forms.ModelForm):
    class Meta:
        model = ConsultaDocumento
        fields = ['tipo', 'titulo', 'arquivo']
        widgets = {
            'tipo':    forms.Select(attrs={'class': 'form-input'}),
            'titulo':  forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Ex: Hemograma completo'}),
            'arquivo': forms.FileInput(attrs={'class': 'form-input'}),
        }


class ASOForm(forms.ModelForm):
    class Meta:
        model = ASO
        fields = ['tipo_exame', 'resultado', 'restricoes', 'riscos_ocupacionais',
                  'exames_realizados', 'cid', 'validade_dias']
        widgets = {
            'tipo_exame':          forms.Select(attrs={'class': 'form-input'}),
            'resultado':           forms.Select(attrs={'class': 'form-input'}),
            'restricoes':          forms.Textarea(attrs={'class': 'form-input', 'rows': 2}),
            'riscos_ocupacionais': forms.Textarea(attrs={'class': 'form-input', 'rows': 2}),
            'exames_realizados':   forms.Textarea(attrs={'class': 'form-input', 'rows': 2}),
            'cid':                 forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Z56.0'}),
            'validade_dias':       forms.NumberInput(attrs={'class': 'form-input', 'min': 30}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['restricoes'].required = False
        self.fields['riscos_ocupacionais'].required = False
        self.fields['exames_realizados'].required = False
        self.fields['cid'].required = False
