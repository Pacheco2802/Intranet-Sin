import hashlib
from django.conf import settings
from django.db import models
from django.utils import timezone
from core.encryption import EncryptedCharField
from core.validators import validate_file_extension, validate_file_size


def _cpf_hash(cpf: str) -> str:
    digits = ''.join(c for c in (cpf or '') if c.isdigit())
    return hashlib.sha256(digits.encode()).hexdigest() if digits else ''


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
                 ('A', 'Andamento de Processo'), ('M', 'Médico do Trabalho')],
    )
    is_retorno = models.BooleanField('É retorno?', default=False)
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
