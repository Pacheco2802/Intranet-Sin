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
    leaders = models.ManyToManyField(
        'CustomUser', blank=True,
        verbose_name='Líderes', related_name='led_departments',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def leader(self):
        return self.leaders.first()

    class Meta:
        verbose_name = 'Departamento'
        verbose_name_plural = 'Departamentos'
        ordering = ['name']

    def __str__(self):
        return self.name


class CustomUser(AbstractUser):
    class Role(models.TextChoices):
        PRESIDENTE = 'PRESIDENTE', 'Presidente'
        COORD_GERAL = 'COORD_GERAL', 'Coord. Geral'
        DIRETOR = 'DIRETOR', 'Diretor'
        ADMIN_TI = 'ADMIN_TI', 'Administrador TI'
        LIDER = 'LIDER', 'Líder'
        COLABORADOR = 'COLABORADOR', 'Colaborador'

    email = models.EmailField('E-mail', unique=True)
    departments = models.ManyToManyField(
        Department, blank=True,
        verbose_name='Departamentos', related_name='users'
    )
    role = models.CharField('Cargo', max_length=20, choices=Role.choices, default=Role.COLABORADOR)
    avatar = models.ImageField('Avatar', upload_to='avatars/', null=True, blank=True)
    phone = EncryptedCharField('Telefone', max_length=200, blank=True)
    bio = models.TextField('Bio', blank=True)
    birth_date = EncryptedDateField('Data de nascimento', null=True, blank=True)
    is_approved = models.BooleanField('Aprovado', default=False)
    can_post_comunicado   = models.BooleanField('Pode criar comunicados', default=False)
    can_access_consultas  = models.BooleanField('Acesso à Agenda Médica', default=False)
    is_aprovador_diretoria = models.BooleanField('Aprova atividades de diretoria', default=False)
    valor_hora_diretoria = models.DecimalField(
        'Valor/hora diretoria', max_digits=8, decimal_places=2, null=True, blank=True,
        help_text='Opcional. Se vazio, usa o valor padrão do módulo Financeiro.'
    )
    nextqs_agent_id = models.CharField('Agent ID NextQS', max_length=50, blank=True)
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
        return self.role in (self.Role.PRESIDENTE, self.Role.COORD_GERAL)

    @property
    def is_lider(self):
        return self.role == self.Role.LIDER

    @property
    def can_manage_users(self):
        return self.role == self.Role.ADMIN_TI

    @property
    def department(self):
        return self.departments.first()

    @property
    def can_see_all(self):
        return self.role in (self.Role.ADMIN_TI, self.Role.PRESIDENTE, self.Role.COORD_GERAL, self.Role.DIRETOR, self.Role.LIDER)

    @property
    def is_financeiro(self):
        return self.is_admin_ti or self.departments.filter(slug='financeiro').exists()

    @property
    def is_diretor_restrito(self):
        """Diretor 'puro': só acessa as abas de atividade/reembolso. Não pega ADMIN_TI,
        aprovador de diretoria (Thabata) nem dept Financeiro, que precisam de acesso amplo."""
        return (
            self.role == self.Role.DIRETOR
            and not self.is_admin_ti
            and not self.is_aprovador_diretoria
            and not self.is_financeiro
        )

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
        USER_PASSWORD_RESET = 'USER_PASSWORD_RESET', 'Senha redefinida'
        DATA_EXPORT = 'DATA_EXPORT', 'Exportação de dados'
        LGPD_CONSENT = 'LGPD_CONSENT', 'Consentimento LGPD'
        ATENDIMENTO_CREATE = 'ATEND_CREATE', 'Atendimento criado'
        ATENDIMENTO_UPDATE = 'ATEND_UPDATE', 'Atendimento atualizado'
        ATENDIMENTO_CLOSE = 'ATEND_CLOSE', 'Atendimento concluído'
        REEMB_CREATE = 'REEMB_CREATE', 'Reembolso solicitado'
        REEMB_APPROVE = 'REEMB_APPROVE', 'Reembolso aprovado'
        REEMB_PAY = 'REEMB_PAY', 'Reembolso pago'
        REEMB_REJECT = 'REEMB_REJECT', 'Reembolso rejeitado'
        DIRAT_CREATE = 'DIRAT_CREATE', 'Atividade de diretoria criada'
        DIRAT_APPROVE = 'DIRAT_APPROVE', 'Atividade de diretoria aprovada'
        DIRAT_REJECT = 'DIRAT_REJECT', 'Atividade de diretoria rejeitada'
        DIRAT_PAY = 'DIRAT_PAY', 'Pagamento de diretoria realizado'

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
        CARD_COMMENT = 'CARD_COMMENT', 'Comentário em card'
        CARD_MOVED = 'CARD_MOVED', 'Card movido de coluna'
        EVENT_INVITE = 'EVENT_INVITE', 'Convite para evento'
        EVENT_REMINDER = 'EVENT_REMINDER', 'Lembrete de evento'
        REEMBOLSO_NOVO = 'REEMBOLSO_NOVO', 'Novo reembolso para análise'
        REEMBOLSO_STATUS = 'REEMBOLSO_STATUS', 'Atualização do seu reembolso'
        DIRETORIA_NOVA = 'DIRETORIA_NOVA', 'Nova atividade para aprovar'
        DIRETORIA_STATUS = 'DIRETORIA_STATUS', 'Atualização da sua atividade'
        DIRETORIA_PAGO = 'DIRETORIA_PAGO', 'Pagamento de diretoria realizado'
        PROJETO_NOVO = 'PROJETO_NOVO', 'Você foi incluído em um projeto'
        PROJETO_FIM = 'PROJETO_FIM', 'Projeto finalizado'

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
