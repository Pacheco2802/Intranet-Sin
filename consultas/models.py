import datetime

from django.conf import settings
from django.db import models

from core.validators import validate_file_extension, validate_file_size


class Doctor(models.Model):
    name   = models.CharField('Nome', max_length=100)
    room   = models.CharField('Sala', max_length=50, blank=True)
    color  = models.CharField('Cor', max_length=7, default='#1e3a5f')
    user   = models.OneToOneField(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='doctor_profile',
        verbose_name='Usuário vinculado',
    )
    active = models.BooleanField('Ativo', default=True)
    order  = models.SmallIntegerField('Ordem', default=0)

    class Meta:
        verbose_name = 'Médico'
        verbose_name_plural = 'Médicos'
        ordering = ['order', 'name']

    def __str__(self):
        return self.name


class Consulta(models.Model):
    class Status(models.TextChoices):
        AGENDADO   = 'agendado',    'Agendado'
        CONFIRMADO = 'confirmado',  'Confirmado'
        PRESENTE   = 'presente',    'Presente'
        FALTOU     = 'faltou',      'Faltou'
        CANCELADO  = 'cancelado',   'Cancelado'
        REMARCADO  = 'remarcado',   'Remarcado'
        FINALIZADO = 'finalizado',  'Finalizado'

    doctor           = models.ForeignKey(Doctor, on_delete=models.PROTECT,
                                         verbose_name='Médico', related_name='consultas')
    patient_name     = models.CharField('Nome do paciente', max_length=200)
    patient_cpf      = models.CharField('CPF', max_length=20, blank=True)
    patient_phone    = models.CharField('Telefone', max_length=30, blank=True)
    date             = models.DateField('Data')
    time             = models.TimeField('Horário')
    duration_minutes = models.SmallIntegerField('Duração (min)', default=30)
    status           = models.CharField('Status', max_length=12,
                                        choices=Status.choices, default=Status.AGENDADO)
    notes            = models.TextField('Observações', blank=True)
    rescheduled_to   = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='rescheduled_from', verbose_name='Remarcada para',
    )
    created_by       = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name='consultas_criadas', verbose_name='Criado por',
    )
    created_at       = models.DateTimeField(auto_now_add=True)
    updated_at       = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Consulta'
        verbose_name_plural = 'Consultas'
        ordering = ['date', 'time']

    def __str__(self):
        return f'{self.patient_name} — {self.date} {self.time}'

    @property
    def status_color(self):
        return {
            'agendado':   'blue',
            'confirmado': 'indigo',
            'presente':   'green',
            'faltou':     'red',
            'cancelado':  'gray',
            'remarcado':  'amber',
            'finalizado': 'teal',
        }.get(self.status, 'gray')


class Atendimento(models.Model):
    """Prontuário clínico vinculado a uma consulta."""
    consulta         = models.OneToOneField(Consulta, on_delete=models.CASCADE,
                                            related_name='atendimento', verbose_name='Consulta')
    # Sinais vitais
    pressao_arterial = models.CharField('Pressão arterial', max_length=10, blank=True)
    peso             = models.DecimalField('Peso (kg)', max_digits=5, decimal_places=1,
                                           null=True, blank=True)
    altura           = models.DecimalField('Altura (m)', max_digits=4, decimal_places=2,
                                           null=True, blank=True)
    # Dados clínicos
    queixa_principal = models.TextField('Queixa principal', blank=True)
    anamnese         = models.TextField('Anamnese / Histórico', blank=True)
    exame_clinico    = models.TextField('Exame clínico', blank=True)
    diagnostico      = models.TextField('Diagnóstico / Impressão', blank=True)
    cid              = models.CharField('CID-10', max_length=10, blank=True)
    conduta          = models.TextField('Conduta', blank=True)
    # Finalização
    finalizado       = models.BooleanField('Finalizado', default=False)
    finalizado_em    = models.DateTimeField(null=True, blank=True)
    finalizado_por   = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='atendimentos_finalizados',
    )
    created_at       = models.DateTimeField(auto_now_add=True)
    updated_at       = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Prontuário'
        verbose_name_plural = 'Prontuários'

    def __str__(self):
        return f'Prontuário — {self.consulta}'


class ConsultaDocumento(models.Model):
    """Arquivos anexados a uma consulta (exames, receitas, laudos, etc.)."""
    class Tipo(models.TextChoices):
        EXAME          = 'exame',          'Exame / Laudo'
        RECEITA        = 'receita',        'Receita'
        ATESTADO       = 'atestado',       'Atestado'
        ENCAMINHAMENTO = 'encaminhamento', 'Encaminhamento'
        OUTRO          = 'outro',          'Outro'

    consulta      = models.ForeignKey(Consulta, on_delete=models.CASCADE,
                                      related_name='documentos', verbose_name='Consulta')
    tipo          = models.CharField('Tipo', max_length=20,
                                     choices=Tipo.choices, default=Tipo.OUTRO)
    titulo        = models.CharField('Título', max_length=200)
    arquivo       = models.FileField(
        'Arquivo', upload_to='consultas/%Y/%m/',
        validators=[validate_file_extension, validate_file_size],
    )
    nome_original = models.CharField(max_length=255)
    enviado_por   = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name='documentos_consulta',
    )
    created_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Documento'
        verbose_name_plural = 'Documentos'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.get_tipo_display()} — {self.titulo}'


class ASO(models.Model):
    """Atestado de Saúde Ocupacional."""
    class TipoExame(models.TextChoices):
        ADMISSIONAL    = 'admissional',     'Admissional'
        PERIODICO      = 'periodico',       'Periódico'
        RETORNO        = 'retorno',         'Retorno ao Trabalho'
        MUDANCA_FUNCAO = 'mudanca_funcao',  'Mudança de Função'
        DEMISSIONAL    = 'demissional',     'Demissional'

    class Resultado(models.TextChoices):
        APTO             = 'apto',           'Apto'
        APTO_COM_RESTRICAO = 'apto_restricao', 'Apto com Restrição'
        INAPTO           = 'inapto',         'Inapto'

    consulta            = models.OneToOneField(Consulta, on_delete=models.CASCADE,
                                               related_name='aso', verbose_name='Consulta')
    tipo_exame          = models.CharField('Tipo de exame', max_length=20, choices=TipoExame.choices)
    resultado           = models.CharField('Resultado', max_length=15, choices=Resultado.choices)
    restricoes          = models.TextField('Restrições', blank=True)
    riscos_ocupacionais = models.TextField('Riscos ocupacionais', blank=True)
    exames_realizados   = models.TextField('Exames realizados', blank=True)
    cid                 = models.CharField('CID-10', max_length=10, blank=True)
    validade_dias       = models.SmallIntegerField('Validade (dias)', default=365)
    data_emissao        = models.DateField('Data de emissão', auto_now_add=True)
    created_by          = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name='asos_emitidos',
    )
    updated_at          = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'ASO'
        verbose_name_plural = 'ASOs'

    def __str__(self):
        return f'ASO — {self.consulta.patient_name} ({self.get_tipo_exame_display()})'

    @property
    def proximo_exame(self):
        return self.data_emissao + datetime.timedelta(days=self.validade_dias)
