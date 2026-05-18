from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError
from django.utils.text import slugify
from .models import CustomUser, Department, Team


class LoginForm(forms.Form):
    email = forms.EmailField(label='E-mail', widget=forms.EmailInput(attrs={'autofocus': True}))
    password = forms.CharField(label='Senha', widget=forms.PasswordInput)


class RegisterForm(forms.Form):
    first_name = forms.CharField(label='Nome', max_length=150)
    last_name = forms.CharField(label='Sobrenome', max_length=150)
    email = forms.EmailField(label='E-mail')
    password1 = forms.CharField(label='Senha', widget=forms.PasswordInput, min_length=8)
    password2 = forms.CharField(label='Confirmar senha', widget=forms.PasswordInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-input'

    def clean_email(self):
        email = self.cleaned_data['email'].lower()
        if CustomUser.objects.filter(email__iexact=email).exists():
            raise ValidationError('Este e-mail já está cadastrado.')
        return email

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get('password1')
        p2 = cleaned.get('password2')
        if p1 and p2 and p1 != p2:
            self.add_error('password2', 'As senhas não coincidem.')
        return cleaned


class UserCreateForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = CustomUser
        fields = ('username', 'first_name', 'last_name', 'email', 'role', 'department', 'phone')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-input'


class UserEditForm(forms.ModelForm):
    class Meta:
        model = CustomUser
        fields = ('first_name', 'last_name', 'email', 'role', 'department', 'phone', 'bio', 'avatar', 'is_active', 'is_approved')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-input'


class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ('name', 'description', 'color', 'icon', 'leader')
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input'}),
            'description': forms.Textarea(attrs={'rows': 2, 'class': 'form-input'}),
            'color': forms.TextInput(attrs={'type': 'color', 'class': 'form-input h-10 p-1 cursor-pointer'}),
            'icon': forms.TextInput(attrs={'class': 'form-input', 'placeholder': '🏢'}),
            'leader': forms.Select(attrs={'class': 'form-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['leader'].queryset = CustomUser.objects.filter(
            is_active=True, is_approved=True
        ).order_by('first_name', 'last_name')
        self.fields['leader'].empty_label = 'Sem líder definido'
        self.fields['leader'].required = False

    def save(self, commit=True):
        dept = super().save(commit=False)
        if not dept.slug:
            dept.slug = slugify(dept.name)
        # ensure slug uniqueness
        base = dept.slug
        n = 1
        qs = Department.objects.exclude(pk=dept.pk) if dept.pk else Department.objects.all()
        while qs.filter(slug=dept.slug).exists():
            dept.slug = f'{base}-{n}'
            n += 1
        if commit:
            dept.save()
        return dept


class TeamForm(forms.ModelForm):
    class Meta:
        model = Team
        fields = ('name',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['name'].widget.attrs['class'] = 'form-input'
        self.fields['name'].label = 'Nome da equipe'


class ApproveUserForm(forms.Form):
    role = forms.ChoiceField(
        label='Cargo',
        choices=CustomUser.Role.choices,
        initial=CustomUser.Role.COLABORADOR,
        widget=forms.Select(attrs={'class': 'form-input'}),
    )
    department = forms.ModelChoiceField(
        label='Departamento',
        queryset=Department.objects.all().order_by('name'),
        required=False,
        empty_label='Sem departamento',
        widget=forms.Select(attrs={'class': 'form-input'}),
    )


class ProfileForm(forms.ModelForm):
    class Meta:
        model = CustomUser
        fields = ('first_name', 'last_name', 'email', 'phone', 'birth_date', 'bio', 'avatar')
        widgets = {
            'birth_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-input'
