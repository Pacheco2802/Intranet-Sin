from django.conf import settings
from django.db import models
from django.utils import timezone


class Conversation(models.Model):
    participants = models.ManyToManyField(
        settings.AUTH_USER_MODEL, verbose_name='Participantes', related_name='conversations'
    )
    is_group = models.BooleanField('É grupo', default=False)
    name = models.CharField('Nome do grupo', max_length=100, blank=True)
    department = models.ForeignKey(
        'core.Department', on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name='Departamento', related_name='conversations'
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name='created_conversations', verbose_name='Criado por'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Conversa'
        verbose_name_plural = 'Conversas'
        ordering = ['-updated_at']

    def __str__(self):
        if self.is_group:
            return self.name or f'Grupo #{self.pk}'
        return f'Conversa #{self.pk}'

    def get_display_name(self, for_user):
        if self.is_group:
            return self.name or f'Grupo #{self.pk}'
        other = self.participants.exclude(pk=for_user.pk).first()
        return str(other) if other else str(self)

    def get_last_message(self):
        return self.messages.filter(is_deleted=False).order_by('-sent_at').first()

    def unread_count(self, user):
        return self.messages.filter(
            is_deleted=False
        ).exclude(
            reads__user=user
        ).exclude(
            sender=user
        ).count()


class Message(models.Model):
    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name='messages', verbose_name='Conversa'
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sent_messages', verbose_name='Remetente'
    )
    content = models.TextField('Mensagem')
    sent_at = models.DateTimeField('Enviada em', default=timezone.now)
    is_deleted = models.BooleanField('Apagada', default=False)

    class Meta:
        verbose_name = 'Mensagem'
        verbose_name_plural = 'Mensagens'
        ordering = ['sent_at']

    def __str__(self):
        return f'{self.sender}: {self.content[:50]}'


class MessageRead(models.Model):
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='reads')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='message_reads')
    read_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('message', 'user')
        verbose_name = 'Leitura de mensagem'
