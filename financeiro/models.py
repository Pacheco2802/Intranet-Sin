from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.validators import validate_file_extension, validate_file_size


class ParametroFinanceiro(models.Model):
    """Configuração única (singleton) do módulo financeiro."""
    valor_hora_diretoria_padrao = models.DecimalField(
        'Valor/hora diretoria (padrão)', max_digits=8, decimal_places=2, default=0
    )
    teto_horas_mensal = models.DecimalField(
        'Teto de horas por mês', max_digits=5, decimal_places=2, default=Decimal('32')
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Parâmetro Financeiro'
        verbose_name_plural = 'Parâmetros Financeiros'

    def __str__(self):
        return 'Parâmetros do Financeiro'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


def valor_hora_efetivo(diretor):
    """Valor/hora do diretor (override individual) ou o padrão global."""
    return diretor.valor_hora_diretoria or ParametroFinanceiro.get().valor_hora_diretoria_padrao


class Reembolso(models.Model):
    class Status(models.TextChoices):
        PENDENTE = 'PENDENTE', 'Aguardando pagamento'
        PAGO = 'PAGO', 'Pago'
        REJEITADO = 'REJEITADO', 'Rejeitado'

    solicitante = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='reembolsos', verbose_name='Solicitante',
    )
    titulo = models.CharField('Título', max_length=200)
    descricao = models.TextField('Descrição', blank=True)
    valor = models.DecimalField('Valor (R$)', max_digits=10, decimal_places=2)
    papel_assinado = models.FileField(
        'Papel assinado', upload_to='financeiro/reembolsos/%Y/%m/',
        validators=[validate_file_extension, validate_file_size],
    )
    comprovante = models.FileField(
        'Comprovante de pagamento', upload_to='financeiro/reembolsos/%Y/%m/',
        validators=[validate_file_extension, validate_file_size],
    )
    status = models.CharField('Status', max_length=10, choices=Status.choices, default=Status.PENDENTE)
    pago_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reembolsos_pagos', verbose_name='Pago por',
    )
    pago_em = models.DateTimeField('Pago em', null=True, blank=True)
    motivo_rejeicao = models.TextField('Motivo da rejeição', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Reembolso'
        verbose_name_plural = 'Reembolsos'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.titulo} — {self.solicitante}'

    @property
    def status_color(self):
        return {
            self.Status.PENDENTE: '#f59e0b',
            self.Status.PAGO: '#16a34a',
            self.Status.REJEITADO: '#ef4444',
        }.get(self.status, '#6b7280')


class PagamentoDiretoria(models.Model):
    """Consolidação mensal por diretor, criada quando o financeiro dá a baixa."""
    diretor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='pagamentos_diretoria', verbose_name='Diretor',
    )
    competencia = models.DateField('Competência (mês)')  # sempre dia 1º do mês
    horas_totais = models.DecimalField('Horas aprovadas', max_digits=7, decimal_places=2, default=0)
    horas_pagas = models.DecimalField('Horas pagas (com teto)', max_digits=7, decimal_places=2, default=0)
    valor_hora = models.DecimalField('Valor/hora aplicado', max_digits=8, decimal_places=2, default=0)
    valor_total = models.DecimalField('Valor total (R$)', max_digits=10, decimal_places=2, default=0)
    pago_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name='pagamentos_diretoria_baixados', verbose_name='Pago por',
    )
    pago_em = models.DateTimeField('Pago em', default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Pagamento de Diretoria'
        verbose_name_plural = 'Pagamentos de Diretoria'
        ordering = ['-competencia', 'diretor']
        unique_together = ('diretor', 'competencia')

    def __str__(self):
        return f'{self.diretor} — {self.competencia:%m/%Y}'


class AtividadeDiretoria(models.Model):
    class Status(models.TextChoices):
        PENDENTE = 'PENDENTE', 'Pendente'
        APROVADA = 'APROVADA', 'Aprovada'
        REJEITADA = 'REJEITADA', 'Rejeitada'
        PAGA = 'PAGA', 'Paga'

    diretor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='atividades_diretoria', verbose_name='Diretor',
    )
    data_atividade = models.DateField('Data da atividade')
    titulo = models.CharField('Título / evento', max_length=200)
    descricao = models.TextField('O que foi feito')
    horas = models.DecimalField('Horas', max_digits=5, decimal_places=2)
    comprovante = models.FileField(
        'Comprovação de presença', upload_to='financeiro/diretoria/%Y/%m/',
        validators=[validate_file_extension, validate_file_size],
    )
    competencia = models.DateField('Competência (mês)', editable=False)  # dia 1º do mês
    status = models.CharField('Status', max_length=10, choices=Status.choices, default=Status.PENDENTE)
    aprovado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='atividades_aprovadas', verbose_name='Aprovado por',
    )
    aprovado_em = models.DateTimeField('Aprovado em', null=True, blank=True)
    horas_aprovadas = models.DecimalField(
        'Horas aprovadas', max_digits=5, decimal_places=2, null=True, blank=True,
        help_text='Definido na aprovação. Pode ser menor que as horas lançadas (aprovação parcial).',
    )
    motivo_rejeicao = models.TextField('Motivo da rejeição', blank=True)
    pagamento = models.ForeignKey(
        PagamentoDiretoria, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='atividades', verbose_name='Pagamento',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Atividade de Diretoria'
        verbose_name_plural = 'Atividades de Diretoria'
        ordering = ['-data_atividade', '-created_at']

    def __str__(self):
        return f'{self.titulo} — {self.diretor}'

    def save(self, *args, **kwargs):
        if self.data_atividade:
            self.competencia = self.data_atividade.replace(day=1)
        super().save(*args, **kwargs)

    @property
    def status_color(self):
        return {
            self.Status.PENDENTE: '#f59e0b',
            self.Status.APROVADA: '#3b82f6',
            self.Status.REJEITADA: '#ef4444',
            self.Status.PAGA: '#16a34a',
        }.get(self.status, '#6b7280')

    @property
    def horas_efetivas(self):
        """Horas que valem para pagamento: as aprovadas (se já aprovada/paga), senão as lançadas."""
        if self.status in (self.Status.APROVADA, self.Status.PAGA) and self.horas_aprovadas is not None:
            return self.horas_aprovadas
        return self.horas

    @property
    def aprovacao_parcial(self):
        """True se foi aprovada por menos horas do que as lançadas."""
        return (
            self.status in (self.Status.APROVADA, self.Status.PAGA)
            and self.horas_aprovadas is not None
            and self.horas_aprovadas < self.horas
        )
