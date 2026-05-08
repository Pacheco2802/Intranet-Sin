from django.conf import settings
from django.db import models
from django.utils import timezone
from core.models import Department


class Comunicado(models.Model):
    title = models.CharField('Título', max_length=200)
    content = models.TextField('Conteúdo')
    is_pinned = models.BooleanField('Fixar', default=False)
    is_published = models.BooleanField('Publicado', default=False)
    published_at = models.DateTimeField('Publicado em', blank=True, null=True)
    expires_at = models.DateTimeField('Expira em', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='comunicados',
        verbose_name='Autor',
    )
    departments = models.ManyToManyField(
        Department,
        blank=True,
        verbose_name='Departamentos',
        help_text='Deixe em branco para enviar a todos',
    )

    class Meta:
        verbose_name = 'Comunicado'
        verbose_name_plural = 'Comunicados'
        ordering = ['-is_pinned', '-published_at']

    def __str__(self):
        return self.title

    def publish(self):
        self.is_published = True
        if not self.published_at:
            self.published_at = timezone.now()
        self.save()
