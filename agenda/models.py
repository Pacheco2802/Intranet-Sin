from django.conf import settings
from django.db import models
from django.utils import timezone


class Event(models.Model):
    title = models.CharField('Título', max_length=200)
    description = models.TextField('Descrição', blank=True)
    location = models.CharField('Local', max_length=200, blank=True)
    start_datetime = models.DateTimeField('Início')
    end_datetime = models.DateTimeField('Término', null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='created_events', verbose_name='Criado por',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Evento'
        verbose_name_plural = 'Eventos'
        ordering = ['start_datetime']

    def __str__(self):
        return self.title

    @property
    def is_past(self):
        return self.start_datetime < timezone.now()


class EventParticipant(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pendente'
        CONFIRMED = 'CONFIRMED', 'Confirmado'
        DECLINED = 'DECLINED', 'Recusado'

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='participants')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='event_participations',
    )
    status = models.CharField('Confirmação', max_length=10, choices=Status.choices, default=Status.PENDING)
    notified_invite = models.BooleanField(default=False)
    notified_reminder = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Participante'
        verbose_name_plural = 'Participantes'
        unique_together = ('event', 'user')

    def __str__(self):
        return f'{self.user} — {self.event}'
