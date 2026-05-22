import hashlib
import re
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from core.encryption import EncryptedCharField, EncryptedDateField


def _anonymize_ip(ip: str) -> str:
    """Mascara os dois últimos octetos do IPv4 (ou últimos 80 bits do IPv6)."""
    if not ip:
        return ip
    if ':' in ip:
        # IPv6: zera a parte de host (últimos 5 grupos de 4 hex)
        parts = ip.split(':')
        return ':'.join(parts[:3] + ['0', '0', '0', '0', '0'])
    parts = ip.split('.')
    if len(parts) == 4:
        return f'{parts[0]}.{parts[1]}.0.0'
    return ip


class Department(models.Model):
    name = models.CharField('Nome', max_length=100, unique=True)
    slug = models.SlugField(unique=True)
    description = models.TextField('Descrição', blank=True)
    color = models.CharField('Cor', max_length=7, default='#1e3a5f')
    icon = models.CharField('Ícone (emoji)', max_length=10, default='🏢')
    leader = models.ForeignKey(
        'CustomUser', on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name='Líder', related_name='led_departments',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Departamento'
        verbose_name_plural = 'Departamentos'
        ordering = ['name']

    def __str__(self):
        return self.name


class CustomUser(AbstractUser):
    class Role(models.TextChoices):
        PRESIDENTE = 'PRESIDENTE', 'Presidente'
        ADMIN_TI = 'ADMIN_TI', 'Administrador TI'
        LIDER = 'LIDER', 'Líder'
        GERENTE = 'GERENTE', 'Gerente'
        COLABORADOR = 'COLABORADOR', 'Colaborador'

    email = models.EmailField('E-mail', unique=True)
    department = models.ForeignKey(
        Department, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name='Departamento', related_name='users'
    )
    role = models.CharField('Cargo', max_length=20, choices=Role.choices, default=Role.COLABORADOR)
    avatar = models.ImageField('Avatar', upload_to='avatars/', null=True, blank=True)
    phone = EncryptedCharField('Telefone', max_length=200, blank=True)
    bio = models.TextField('Bio', blank=True)
    birth_date = EncryptedDateField('Data de nascimento', null=True, blank=True)
    is_approved = models.BooleanField('Aprovado', default=False)
    lgpd_consent = models.BooleanField('Consentimento LGPD', default=False)
    lgpd_consent_date = models.DateTimeField('Data do consentimento', null=True, blank=True)
    created_by = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name='Criado por', related_name='created_users'
    )

    class Meta:
        verbose_name = 'Usuário'
        verbose_name_plural = 'Usuários'

    def __str__(self):
        return self.get_full_name() or self.username

    @property
    def is_admin_ti(self):
        return self.role == self.Role.ADMIN_TI

    @property
    def is_presidente(self):
        return self.role == self.Role.PRESIDENTE

    @property
    def is_lider(self):
        return self.role == self.Role.LIDER

    @property
    def can_manage_users(self):
        return self.role == self.Role.ADMIN_TI

    @property
    def can_see_all(self):
        return self.role in (self.Role.ADMIN_TI, self.Role.PRESIDENTE)

    def anonymize(self):
        uid = hashlib.sha256(str(self.pk).encode()).hexdigest()[:8]
        self.first_name = 'Usuário'
        self.last_name = 'Removido'
        self.email = f'removido_{uid}@anonimizado.local'
        self.phone = ''
        self.bio = ''
        self.avatar = None
        self.is_active = False
        self.is_approved = False
        self.lgpd_consent = False
        self.save()

    @staticmethod
    def generate_username(email):
        base = re.sub(r'[^a-z0-9_]', '_', email.split('@')[0].lower())
        username = base
        counter = 1
        while CustomUser.objects.filter(username=username).exists():
            username = f'{base}{counter}'
            counter += 1
        return username


class Team(models.Model):
    name = models.CharField('Nome', max_length=100)
    department = models.OneToOneField(
        Department, on_delete=models.CASCADE, null=True, blank=True,
        verbose_name='Departamento', related_name='team'
    )
    is_general = models.BooleanField('Equipe Geral', default=False)
    # is_protected: Geral e equipes de departamento não podem ser excluídas
    is_protected = models.BooleanField('Protegida', default=False)
    members = models.ManyToManyField(
        CustomUser, blank=True, verbose_name='Membros', related_name='teams'
    )
    conversation = models.OneToOneField(
        'mensagens.Conversation', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='team', verbose_name='Chat da equipe'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Equipe'
        verbose_name_plural = 'Equipes'
        ordering = ['-is_general', 'name']

    def __str__(self):
        return self.name

    def ensure_conversation(self):
        """Creates the group conversation if it doesn't exist yet."""
        if self.conversation_id:
            return self.conversation
        from mensagens.models import Conversation
        conv = Conversation.objects.create(
            is_group=True,
            name=f'Equipe: {self.name}',
            created_by=None,
        )
        for member in self.members.all():
            conv.participants.add(member)
        self.conversation = conv
        self.save(update_fields=['conversation'])
        return conv


class LGPDConsent(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='consents')
    policy_version = models.CharField('Versão da política', max_length=20, default='1.0')
    consent_date = models.DateTimeField('Data', default=timezone.now)
    ip_address = models.GenericIPAddressField('IP')

    class Meta:
        verbose_name = 'Consentimento LGPD'
        verbose_name_plural = 'Consentimentos LGPD'
        ordering = ['-consent_date']

    def __str__(self):
        return f'{self.user} - {self.consent_date:%d/%m/%Y}'


class AuditLog(models.Model):
    class Action(models.TextChoices):
        LOGIN = 'LOGIN', 'Login'
        LOGOUT = 'LOGOUT', 'Logout'
        MSG_SEND = 'MSG_SEND', 'Mensagem enviada'
        MSG_DELETE = 'MSG_DELETE', 'Mensagem apagada'
        CARD_CREATE = 'CARD_CREATE', 'Card criado'
        CARD_UPDATE = 'CARD_UPDATE', 'Card atualizado'
        CARD_DELETE = 'CARD_DELETE', 'Card excluído'
        USER_CREATE = 'USER_CREATE', 'Usuário criado'
        USER_REGISTER = 'USER_REGISTER', 'Cadastro solicitado'
        USER_APPROVE = 'USER_APPROVE', 'Usuário aprovado'
        USER_REJECT = 'USER_REJECT', 'Usuário rejeitado'
        USER_EDIT = 'USER_EDIT', 'Usuário editado'
        USER_DEACTIVATE = 'USER_DEACTIVATE', 'Usuário desativado'
        USER_ANONYMIZE = 'USER_ANONYMIZE', 'Usuário anonimizado'
        DATA_EXPORT = 'DATA_EXPORT', 'Exportação de dados'
        LGPD_CONSENT = 'LGPD_CONSENT', 'Consentimento LGPD'
        ATENDIMENTO_CREATE = 'ATEND_CREATE', 'Atendimento criado'
        ATENDIMENTO_UPDATE = 'ATEND_UPDATE', 'Atendimento atualizado'
        ATENDIMENTO_CLOSE = 'ATEND_CLOSE', 'Atendimento concluído'

    user = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name='Usuário', related_name='audit_logs'
    )
    action = models.CharField('Ação', max_length=30, choices=Action.choices)
    resource_type = models.CharField('Tipo do recurso', max_length=50, blank=True)
    resource_id = models.CharField('ID do recurso', max_length=50, blank=True)
    ip_address = models.GenericIPAddressField('IP', null=True, blank=True)
    timestamp = models.DateTimeField('Data/Hora', default=timezone.now)
    detail = models.JSONField('Detalhes', default=dict, blank=True)

    class Meta:
        verbose_name = 'Log de Auditoria'
        verbose_name_plural = 'Logs de Auditoria'
        ordering = ['-timestamp']

    def __str__(self):
        return f'{self.user} - {self.action} - {self.timestamp:%d/%m/%Y %H:%M}'

    @classmethod
    def log(cls, user, action, resource_type='', resource_id='', ip=None, **detail):
        cls.objects.create(
            user=user,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id),
            ip_address=_anonymize_ip(ip) if ip else None,
            detail=detail,
        )


class Notification(models.Model):
    class Type(models.TextChoices):
        CARD_ASSIGNED = 'CARD_ASSIGNED', 'Card atribuído a você'
        CARD_DEPT = 'CARD_DEPT', 'Card criado na sua área'
        CARD_CROSS = 'CARD_CROSS', 'Card entre departamentos'
        EVENT_INVITE = 'EVENT_INVITE', 'Convite para evento'
        EVENT_REMINDER = 'EVENT_REMINDER', 'Lembrete de evento'

    user = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE,
        related_name='notifications', verbose_name='Destinatário',
    )
    actor = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='sent_notifications', verbose_name='Quem gerou',
    )
    type = models.CharField('Tipo', max_length=20, choices=Type.choices)
    title = models.CharField('Título', max_length=200)
    body = models.TextField('Mensagem', blank=True)
    link = models.CharField('Link', max_length=500, blank=True)
    is_read = models.BooleanField('Lida', default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Notificação'
        verbose_name_plural = 'Notificações'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user} — {self.title}'

    @classmethod
    def send(cls, user, actor, ntype, title, body='', link=''):
        if user == actor:
            return
        cls.objects.create(
            user=user, actor=actor, type=ntype,
            title=title, body=body, link=link,
        )
