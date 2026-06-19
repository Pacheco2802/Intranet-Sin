from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils.text import slugify
from .models import CustomUser, Department, Team

_AVATAR_MAX_SIZE = 2 * 1024 * 1024  # 2 MB
_AVATAR_ALLOWED = {'image/jpeg', 'image/png', 'image/gif', 'image/webp'}


def _validate_avatar(f):
    if f and hasattr(f, 'content_type'):
        if f.content_type not in _AVATAR_ALLOWED:
            raise ValidationError('Apenas imagens JPEG, PNG, GIF ou WebP são permitidas.')
        if f.size > _AVATAR_MAX_SIZE:
            raise ValidationError('A imagem não pode exceder 2 MB.')


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

    def clean_password1(self):
        password = self.cleaned_data.get('password1')
        if password:
            try:
                validate_password(password)
            except ValidationError as e:
                raise ValidationError(e.messages)
        return password

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
        fields = ('username', 'first_name', 'last_name', 'email', 'role', 'departments', 'phone')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-input'


class UserEditForm(forms.ModelForm):
    class Meta:
        model = CustomUser
        fields = ('first_name', 'last_name', 'email', 'role', 'departments', 'phone', 'bio', 'avatar', 'is_active', 'is_approved', 'can_post_comunicado', 'can_access_consultas', 'is_aprovador_diretoria')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-input'

    def clean_avatar(self):
        avatar = self.cleaned_data.get('avatar')
        _validate_avatar(avatar)
        return avatar


class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ('name', 'description', 'color', 'icon', 'leaders')
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input'}),
            'description': forms.Textarea(attrs={'rows': 2, 'class': 'form-input'}),
            'color': forms.TextInput(attrs={'type': 'color', 'class': 'form-input h-10 p-1 cursor-pointer'}),
            'icon': forms.TextInput(attrs={'class': 'form-input', 'placeholder': '🏢'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['leaders'].queryset = CustomUser.objects.filter(
            is_active=True, is_approved=True
        ).order_by('first_name', 'last_name')
        self.fields['leaders'].required = False

    def save(self, commit=True):
        dept = super().save(commit=False)
        if not dept.slug:
            dept.slug = slugify(dept.name)
        base = dept.slug
        n = 1
        qs = Department.objects.exclude(pk=dept.pk) if dept.pk else Department.objects.all()
        while qs.filter(slug=dept.slug).exists():
            dept.slug = f'{base}-{n}'
            n += 1
        if commit:
            dept.save()
            self.save_m2m()
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
        label='Departamento inicial',
        queryset=Department.objects.all().order_by('name'),
        required=False,
        empty_label='Sem departamento',
        widget=forms.Select(attrs={'class': 'form-input'}),
    )


class AdminPasswordResetForm(forms.Form):
    password1 = forms.CharField(
        label='Nova senha',
        widget=forms.PasswordInput(attrs={'class': 'form-input', 'autocomplete': 'new-password'}),
        min_length=8,
    )
    password2 = forms.CharField(
        label='Confirmar nova senha',
        widget=forms.PasswordInput(attrs={'class': 'form-input', 'autocomplete': 'new-password'}),
    )

    def clean_password1(self):
        password = self.cleaned_data.get('password1')
        if password:
            try:
                validate_password(password)
            except ValidationError as e:
                raise ValidationError(e.messages)
        return password

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('password1') and cleaned.get('password2') and cleaned['password1'] != cleaned['password2']:
            self.add_error('password2', 'As senhas não coincidem.')
        return cleaned


class ChangeOwnPasswordForm(forms.Form):
    current_password = forms.CharField(
        label='Senha atual',
        widget=forms.PasswordInput(attrs={'class': 'form-input', 'autocomplete': 'current-password'}),
    )
    password1 = forms.CharField(
        label='Nova senha',
        widget=forms.PasswordInput(attrs={'class': 'form-input', 'autocomplete': 'new-password'}),
        min_length=8,
    )
    password2 = forms.CharField(
        label='Confirmar nova senha',
        widget=forms.PasswordInput(attrs={'class': 'form-input', 'autocomplete': 'new-password'}),
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_current_password(self):
        current = self.cleaned_data.get('current_password')
        if not self.user.check_password(current):
            raise ValidationError('Senha atual incorreta.')
        return current

    def clean_password1(self):
        password = self.cleaned_data.get('password1')
        if password:
            try:
                validate_password(password, user=self.user)
            except ValidationError as e:
                raise ValidationError(e.messages)
        return password

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('password1') and cleaned.get('password2') and cleaned['password1'] != cleaned['password2']:
            self.add_error('password2', 'As senhas não coincidem.')
        return cleaned


class ProfileForm(forms.ModelForm):
    class Meta:
        model = CustomUser
        fields = ('first_name', 'last_name', 'email', 'phone', 'birth_date', 'bio', 'avatar', 'nextqs_agent_id')
        widgets = {
            'birth_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-input'

    def clean_avatar(self):
        avatar = self.cleaned_data.get('avatar')
        _validate_avatar(avatar)
        return avatar
