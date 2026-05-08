from django.conf import settings
from django.db import models
from django.utils import timezone


class Comunicado(models.Model):
    title = models.CharField('Título', max_length=200)
    content = models.TextField('Conteúdo')
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        verbose_name='Autor', related_name='comunicados'
    )
    departments = models.ManyToManyField(
        'core.Department', verbose_name='Departamentos', blank=True,
        help_text='Deixe em branco para enviar a todos'
    )
    is_pinned = models.BooleanField('Fixar', default=False)
    is_published = models.BooleanField('Publicado', default=False)
    published_at = models.DateTimeField('Publicado em', null=True, blank=True)
    expires_at = models.DateTimeField('Expira em', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Comunicado'
        verbose_name_plural = 'Comunicados'
        ordering = ['-is_pinned', '-published_at']

    def __str__(self):
        return self.title

    @property
    def is_active(self):
        now = timezone.now()
        if not self.is_published:
            return False
        if self.expires_at and self.expires_at < now:
            return False
        return True

    def publish(self):
        self.is_published = True
        self.published_at = timezone.now()
        self.save(update_fields=['is_published', 'published_at'])

    def is_visible_to(self, user):
        if not self.is_active:
            return False
        if not self.departments.exists():
            return True
        return self.departments.filter(pk=user.department_id).exists()
