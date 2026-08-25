import hashlib
import secrets
from django.conf import settings
from django.db import models
from django.utils import timezone
from core.encryption import EncryptedCharField
from core.validators import validate_file_extension, validate_file_size


def _cpf_hash(cpf: str) -> str:
    digits = ''.join(c for c in (cpf or '') if c.isdigit())
    return hashlib.sha256(digits.encode()).hexdigest() if digits else ''


# Alfabeto sem caracteres ambíguos (0/O, 1/I/L) para o código digitado no totem
_CODIGO_ALFABETO = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'


def gerar_triagem_credenciais():
    """Gera (token, codigo) para o vínculo público da triagem.

    O token vai no QR do slip; o código curto é digitado no totem. O código é
    único entre os atendimentos ativos do dia (retry na colisão).
    """
    from django.utils.timezone import localdate
    token = secrets.token_urlsafe(24)
    for _ in range(20):
        codigo = ''.join(secrets.choice(_CODIGO_ALFABETO) for _ in range(6))
        existe = Atendimento.objects.filter(
            triagem_codigo=codigo,
            created_at__date=localdate(),
        ).exclude(status__in=[Atendimento.Status.CONCLUIDO, Atendimento.Status.CANCELADO]).exists()
        if not existe:
            return token, codigo
    return token, ''


class Atendimento(models.Model):
    class Status(models.TextChoices):
        TRIAGEM = 'TRIAGEM', 'Na Recepção'
        ENCAMINHADO = 'ENCAMINHADO', 'Encaminhado'
        EM_ANDAMENTO = 'EM_ANDAMENTO', 'Em Andamento'
        CONCLUIDO = 'CONCLUIDO', 'Concluído'
        CANCELADO = 'CANCELADO', 'Cancelado'

    STATUS_COLORS = {
        'TRIAGEM': '#64748b',
        'ENCAMINHADO': '#3b82f6',
        'EM_ANDAMENTO': '#f59e0b',
        'CONCLUIDO': '#22c55e',
        'CANCELADO': '#ef4444',
    }

    cpf = EncryptedCharField('CPF', max_length=200, blank=True)
    cpf_hash = models.CharField('Hash do CPF', max_length=64, blank=True, db_index=True)
    nome_filiado = models.CharField('Nome do filiado', max_length=200, blank=True)
    telefone = EncryptedCharField('Telefone', max_length=200, blank=True)
    email_filiado = models.EmailField('E-mail do filiado', blank=True)

    numero_senha = models.CharField('Nº Senha', max_length=10, blank=True)
    nextqs_fila = models.CharField(
        'Fila NextQS', max_length=1, blank=True,
        choices=[('J', 'Jurídico'), ('P', 'Previdenciário'), ('T', 'Trabalhista'),
                 ('A', 'Andamento de Processo'), ('M', 'Médico do Trabalho'),
                 ('D', 'Denúncia')],
    )
    is_retorno = models.BooleanField('É retorno?', default=False)
    is_preferencial = models.BooleanField('Atendimento preferencial', default=False)
    retorno_de = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='retornos', verbose_name='Retorno do atendimento',
    )

    assunto = models.CharField('Assunto', max_length=200, blank=True)
    is_auto_nextqs = models.BooleanField('Gerado pelo NextQS', default=False)
    descricao = models.TextField('Descrição inicial', blank=True)
    status = models.CharField(
        'Status', max_length=20,
        choices=Status.choices, default=Status.TRIAGEM
    )

    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name='atendimentos_criados', verbose_name='Criado por'
    )
    departamento_atual = models.ForeignKey(
        'core.Department', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='atendimentos_em_curso', verbose_name='Departamento atual'
    )
    responsavel = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='atendimentos_responsavel', verbose_name='Responsável'
    )

    associado = models.ForeignKey(
        'associados.Associado', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='atendimentos', verbose_name='Associado',
    )

    # Triagem pública (QR do slip / totem)
    triagem_token = models.CharField('Token da triagem', max_length=64, blank=True, db_index=True)
    triagem_codigo = models.CharField('Código curto da triagem', max_length=8, blank=True, db_index=True)
    triagem_preenchida_em = models.DateTimeField('Triagem preenchida em', null=True, blank=True)

    created_at = models.DateTimeField('Criado em', auto_now_add=True)
    updated_at = models.DateTimeField('Atualizado em', auto_now=True)
    iniciado_em = models.DateTimeField('Iniciado em', null=True, blank=True)
    concluido_em = models.DateTimeField('Concluído em', null=True, blank=True)

    class Meta:
        verbose_name = 'Atendimento'
        verbose_name_plural = 'Atendimentos'
        ordering = ['-updated_at']

    def save(self, *args, **kwargs):
        self.cpf_hash = _cpf_hash(self.cpf)
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.nome_filiado} — {self.assunto}'

    @property
    def status_color(self):
        return self.STATUS_COLORS.get(self.status, '#64748b')

    @property
    def tempo_espera_min(self):
        if self.iniciado_em and self.created_at:
            return max(0, int((self.iniciado_em - self.created_at).total_seconds() / 60))
        return None

    @property
    def tempo_atendimento_min(self):
        if self.concluido_em and self.iniciado_em:
            return max(0, int((self.concluido_em - self.iniciado_em).total_seconds() / 60))
        return None


class AtendimentoEtapa(models.Model):
    class Tipo(models.TextChoices):
        ABERTURA = 'ABERTURA', 'Abertura'
        NOTA = 'NOTA', 'Anotação'
        ENCAMINHAMENTO = 'ENCAMINHAMENTO', 'Encaminhamento'
        CONCLUSAO = 'CONCLUSAO', 'Conclusão'
        CANCELAMENTO = 'CANCELAMENTO', 'Cancelamento'

    TIPO_ICONS = {
        'ABERTURA': '📋',
        'NOTA': '📝',
        'ENCAMINHAMENTO': '➡️',
        'CONCLUSAO': '✅',
        'CANCELAMENTO': '❌',
    }

    atendimento = models.ForeignKey(
        Atendimento, on_delete=models.CASCADE,
        related_name='etapas', verbose_name='Atendimento'
    )
    tipo = models.CharField('Tipo', max_length=20, choices=Tipo.choices)
    autor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        verbose_name='Autor'
    )
    departamento = models.ForeignKey(
        'core.Department', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='etapas_realizadas', verbose_name='Departamento do autor'
    )
    para_departamento = models.ForeignKey(
        'core.Department', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='encaminhamentos_recebidos', verbose_name='Encaminhar para'
    )
    descricao = models.TextField('Descrição')
    created_at = models.DateTimeField('Registrado em', default=timezone.now)

    class Meta:
        verbose_name = 'Etapa'
        verbose_name_plural = 'Etapas'
        ordering = ['created_at']

    def __str__(self):
        return f'{self.get_tipo_display()} — {self.atendimento}'

    @property
    def tipo_icon(self):
        return self.TIPO_ICONS.get(self.tipo, '•')


class AtendimentoAnexo(models.Model):
    atendimento = models.ForeignKey(
        Atendimento, on_delete=models.CASCADE,
        related_name='anexos', verbose_name='Atendimento'
    )
    etapa = models.ForeignKey(
        AtendimentoEtapa, on_delete=models.CASCADE, null=True, blank=True,
        related_name='anexos', verbose_name='Etapa'
    )
    arquivo = models.FileField(
        'Arquivo', upload_to='atendimentos/%Y/%m/',
        validators=[validate_file_extension, validate_file_size],
    )
    nome_original = models.CharField('Nome do arquivo', max_length=255)
    enviado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        verbose_name='Enviado por'
    )
    created_at = models.DateTimeField('Enviado em', auto_now_add=True)

    class Meta:
        verbose_name = 'Anexo'
        verbose_name_plural = 'Anexos'
        ordering = ['created_at']

    def __str__(self):
        return self.nome_original


class TriagemPublica(models.Model):
    """Triagem preenchida pelo próprio filiado (QR do slip ou totem da recepção).

    Guarda o conteúdo informado e a prova de consentimento LGPD do não-usuário
    (o LGPDConsent do core exige FK de CustomUser).
    """

    class Motivo(models.TextChoices):
        PREVIDENCIARIO = 'P', 'Previdenciário (aposentadoria, INSS, benefícios)'
        TRABALHISTA = 'T', 'Trabalhista (demissão, verbas, direitos)'
        ANDAMENTO = 'A', 'Andamento de processo já em curso'
        MEDICO = 'M', 'Médico do Trabalho'
        DENUNCIA = 'D', 'Denúncia'
        OUTRO = 'O', 'Outro assunto'

    class Origem(models.TextChoices):
        QR = 'QR', 'QR code (celular)'
        TOTEM = 'TOTEM', 'Totem da recepção'

    atendimento = models.OneToOneField(
        Atendimento, on_delete=models.CASCADE,
        related_name='triagem_publica', verbose_name='Atendimento',
    )
    motivo = models.CharField('Motivo', max_length=1, choices=Motivo.choices)
    descricao = models.TextField('Descrição do problema')
    nome_informado = models.CharField('Nome informado', max_length=200, blank=True)
    telefone = EncryptedCharField('Telefone', max_length=200, blank=True)
    email = models.EmailField('E-mail', blank=True)
    cargo = models.CharField('Cargo', max_length=120, blank=True)
    empregador = models.CharField('Empregador', max_length=200, blank=True)
    origem = models.CharField('Origem', max_length=10, choices=Origem.choices, default=Origem.QR)

    lgpd_consent = models.BooleanField('Consentimento LGPD', default=False)
    policy_version = models.CharField('Versão da política', max_length=20, default='1.0')
    consent_ip = models.GenericIPAddressField('IP do consentimento', null=True, blank=True)

    created_at = models.DateTimeField('Enviada em', auto_now_add=True)
    updated_at = models.DateTimeField('Atualizada em', auto_now=True)

    class Meta:
        verbose_name = 'Triagem pública'
        verbose_name_plural = 'Triagens públicas'
        ordering = ['-created_at']

    def __str__(self):
        return f'Triagem — {self.atendimento}'
