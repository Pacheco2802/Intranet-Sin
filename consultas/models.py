from django.conf import settings
from django.db import models


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
        AGENDADO   = 'agendado',   'Agendado'
        CONFIRMADO = 'confirmado', 'Confirmado'
        PRESENTE   = 'presente',   'Presente'
        FALTOU     = 'faltou',     'Faltou'
        CANCELADO  = 'cancelado',  'Cancelado'
        REMARCADO  = 'remarcado',  'Remarcado'

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
        }.get(self.status, 'gray')
