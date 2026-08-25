from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.validators import validate_file_extension, validate_file_size


class Prioridade(models.TextChoices):
    BAIXA = 'BAIXA', 'Baixa'
    MEDIA = 'MEDIA', 'Média'
    ALTA = 'ALTA', 'Alta'
    URGENTE = 'URGENTE', 'Urgente'


PRIORIDADE_COLORS = {
    'BAIXA': '#64748b',
    'MEDIA': '#3b82f6',
    'ALTA': '#f59e0b',
    'URGENTE': '#ef4444',
}


class CategoriaChamado(models.Model):
    """Tipo de chamado de TI (Hardware, Software, Rede...). O assistente de triagem
    conduz o solicitante até uma destas categorias."""
    nome = models.CharField('Nome', max_length=100, unique=True)
    descricao = models.CharField('Descrição', max_length=200, blank=True)
    icone = models.CharField('Ícone', max_length=10, blank=True)  # emoji; vazio = 🛠️
    prioridade_padrao = models.CharField(
        'Prioridade padrão', max_length=10,
        choices=Prioridade.choices, default=Prioridade.MEDIA,
    )
    sla_horas = models.PositiveIntegerField(
        'SLA (horas)', null=True, blank=True,
        help_text='Prazo de atendimento em horas. Vazio = sem prazo.',
    )
    responsavel_padrao = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='categorias_chamado_padrao', verbose_name='Responsável padrão',
    )
    ativo = models.BooleanField('Ativa', default=True)
    ordem = models.PositiveSmallIntegerField('Ordem', default=0)

    class Meta:
        verbose_name = 'Categoria de chamado'
        verbose_name_plural = 'Categorias de chamado'
        ordering = ['ordem', 'nome']

    def __str__(self):
        return f'{self.icone} {self.nome}'.strip()

    @property
    def display_icon(self):
        return self.icone or '🛠️'


class PerguntaTriagem(models.Model):
    """Nó da árvore do assistente guiado: uma pergunta de múltipla escolha."""
    texto = models.CharField('Pergunta', max_length=200)
    ajuda = models.CharField('Texto de ajuda', max_length=200, blank=True)
    is_raiz = models.BooleanField(
        'É a pergunta inicial?', default=False,
        help_text='Marque apenas UMA pergunta como inicial (entrada do assistente).',
    )
    ativo = models.BooleanField('Ativa', default=True)
    ordem = models.PositiveSmallIntegerField('Ordem', default=0)

    class Meta:
        verbose_name = 'Pergunta da triagem'
        verbose_name_plural = 'Perguntas da triagem'
        ordering = ['ordem', 'id']

    def __str__(self):
        return self.texto

    @classmethod
    def raiz(cls):
        return cls.objects.filter(is_raiz=True, ativo=True).order_by('ordem', 'id').first()

    def opcoes_ativas(self):
        return self.opcoes.all()


class OpcaoTriagem(models.Model):
    """Aresta da árvore: uma resposta possível. Leva a OUTRA pergunta OU encerra a
    triagem definindo a categoria final (folha)."""
    pergunta = models.ForeignKey(
        PerguntaTriagem, on_delete=models.CASCADE,
        related_name='opcoes', verbose_name='Pergunta',
    )
    label = models.CharField('Resposta', max_length=200)
    icone = models.CharField('Ícone', max_length=10, blank=True)
    ordem = models.PositiveSmallIntegerField('Ordem', default=0)
    # Destino em XOR: uma próxima pergunta OU uma categoria final.
    proxima_pergunta = models.ForeignKey(
        PerguntaTriagem, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='vem_de_opcoes', verbose_name='Próxima pergunta',
    )
    categoria = models.ForeignKey(
        CategoriaChamado, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='opcoes_triagem', verbose_name='Categoria final',
    )
    prioridade = models.CharField(
        'Prioridade', max_length=10, choices=Prioridade.choices, blank=True,
        help_text='Opcional. Se preenchida, sobrepõe a prioridade padrão da categoria.',
    )

    class Meta:
        verbose_name = 'Opção de resposta'
        verbose_name_plural = 'Opções de resposta'
        ordering = ['ordem', 'id']
        constraints = [
            models.CheckConstraint(
                condition=(
                    (models.Q(proxima_pergunta__isnull=False) & models.Q(categoria__isnull=True))
                    | (models.Q(proxima_pergunta__isnull=True) & models.Q(categoria__isnull=False))
                ),
                name='opcao_triagem_destino_xor',
            ),
        ]

    def __str__(self):
        return f'{self.pergunta} → {self.label}'

    @property
    def is_folha(self):
        return self.categoria_id is not None

    def prioridade_efetiva(self):
        if self.prioridade:
            return self.prioridade
        if self.categoria:
            return self.categoria.prioridade_padrao
        return Prioridade.MEDIA


class Chamado(models.Model):
    class Status(models.TextChoices):
        ABERTO = 'ABERTO', 'Aberto'
        EM_ANDAMENTO = 'EM_ANDAMENTO', 'Em andamento'
        AGUARDANDO = 'AGUARDANDO', 'Aguardando solicitante'
        RESOLVIDO = 'RESOLVIDO', 'Resolvido'
        FECHADO = 'FECHADO', 'Fechado'
        CANCELADO = 'CANCELADO', 'Cancelado'

    STATUS_COLORS = {
        'ABERTO': '#3b82f6',
        'EM_ANDAMENTO': '#f59e0b',
        'AGUARDANDO': '#a855f7',
        'RESOLVIDO': '#22c55e',
        'FECHADO': '#64748b',
        'CANCELADO': '#ef4444',
    }

    codigo = models.CharField('Código', max_length=20, blank=True, db_index=True)
    solicitante = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name='chamados_abertos', verbose_name='Solicitante',
    )
    titulo = models.CharField('Título', max_length=200)
    descricao = models.TextField('Descrição', blank=True)
    categoria = models.ForeignKey(
        CategoriaChamado, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='chamados', verbose_name='Categoria',
    )
    prioridade = models.CharField(
        'Prioridade', max_length=10, choices=Prioridade.choices, default=Prioridade.MEDIA,
    )
    status = models.CharField(
        'Status', max_length=15, choices=Status.choices, default=Status.ABERTO,
    )
    responsavel = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='chamados_responsavel', verbose_name='Responsável (TI)',
    )
    respostas_triagem = models.JSONField('Respostas da triagem', default=list, blank=True)

    created_at = models.DateTimeField('Aberto em', auto_now_add=True)
    updated_at = models.DateTimeField('Atualizado em', auto_now=True)
    iniciado_em = models.DateTimeField('Iniciado em', null=True, blank=True)
    resolvido_em = models.DateTimeField('Resolvido em', null=True, blank=True)

    class Meta:
        verbose_name = 'Chamado'
        verbose_name_plural = 'Chamados'
        ordering = ['-updated_at']

    def __str__(self):
        return f'{self.codigo or "#"} — {self.titulo}'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.codigo:
            ano = (self.created_at or timezone.now()).year
            codigo = f'TI-{ano}-{self.pk:05d}'
            Chamado.objects.filter(pk=self.pk).update(codigo=codigo)
            self.codigo = codigo

    @property
    def status_color(self):
        return self.STATUS_COLORS.get(self.status, '#64748b')

    @property
    def prioridade_color(self):
        return PRIORIDADE_COLORS.get(self.prioridade, '#64748b')

    @property
    def is_aberto(self):
        return self.status not in (
            self.Status.RESOLVIDO, self.Status.FECHADO, self.Status.CANCELADO,
        )

    @property
    def sla_prazo(self):
        if self.categoria_id and self.categoria and self.categoria.sla_horas and self.created_at:
            return self.created_at + timedelta(hours=self.categoria.sla_horas)
        return None

    @property
    def is_atrasado(self):
        prazo = self.sla_prazo
        if not prazo or not self.is_aberto:
            return False
        return timezone.now() > prazo


class ChamadoEtapa(models.Model):
    """Entrada da linha do tempo do chamado: comentário, andamento, mudança de status."""
    class Tipo(models.TextChoices):
        ABERTURA = 'ABERTURA', 'Abertura'
        COMENTARIO = 'COMENTARIO', 'Comentário'
        ANDAMENTO = 'ANDAMENTO', 'Andamento'
        ATRIBUICAO = 'ATRIBUICAO', 'Atribuição'
        STATUS = 'STATUS', 'Mudança de status'
        RESOLUCAO = 'RESOLUCAO', 'Resolução'
        REABERTURA = 'REABERTURA', 'Reabertura'
        CANCELAMENTO = 'CANCELAMENTO', 'Cancelamento'

    TIPO_ICONS = {
        'ABERTURA': '📋',
        'COMENTARIO': '💬',
        'ANDAMENTO': '🔧',
        'ATRIBUICAO': '👤',
        'STATUS': '🔄',
        'RESOLUCAO': '✅',
        'REABERTURA': '↩️',
        'CANCELAMENTO': '❌',
    }

    chamado = models.ForeignKey(
        Chamado, on_delete=models.CASCADE,
        related_name='etapas', verbose_name='Chamado',
    )
    tipo = models.CharField('Tipo', max_length=15, choices=Tipo.choices)
    autor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        verbose_name='Autor',
    )
    descricao = models.TextField('Descrição')
    created_at = models.DateTimeField('Registrado em', default=timezone.now)

    class Meta:
        verbose_name = 'Etapa'
        verbose_name_plural = 'Etapas'
        ordering = ['created_at']

    def __str__(self):
        return f'{self.get_tipo_display()} — {self.chamado}'

    @property
    def tipo_icon(self):
        return self.TIPO_ICONS.get(self.tipo, '•')


class ChamadoAnexo(models.Model):
    chamado = models.ForeignKey(
        Chamado, on_delete=models.CASCADE,
        related_name='anexos', verbose_name='Chamado',
    )
    etapa = models.ForeignKey(
        ChamadoEtapa, on_delete=models.CASCADE, null=True, blank=True,
        related_name='anexos', verbose_name='Etapa',
    )
    arquivo = models.FileField(
        'Arquivo', upload_to='chamados/%Y/%m/',
        validators=[validate_file_extension, validate_file_size],
    )
    nome_original = models.CharField('Nome do arquivo', max_length=255)
    enviado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        verbose_name='Enviado por',
    )
    created_at = models.DateTimeField('Enviado em', auto_now_add=True)

    class Meta:
        verbose_name = 'Anexo'
        verbose_name_plural = 'Anexos'
        ordering = ['created_at']

    def __str__(self):
        return self.nome_original
