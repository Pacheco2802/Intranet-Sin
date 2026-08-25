from django.conf import settings
from django.db import IntegrityError, models

from core.encryption import EncryptedCharField, EncryptedDateField
from core.validators import validate_file_extension, validate_file_size
from atendimento.models import _cpf_hash

# Nome usado pelos stubs criados pelo sync da fila NextQS — tratado como "vazio"
NOME_PLACEHOLDER = 'Aguardando identificação'


class Associado(models.Model):
    class Origem(models.TextChoices):
        RETROATIVO = 'RETROATIVO', 'Migração retroativa'
        RECEPCAO = 'RECEPCAO', 'Recepção'
        TRIAGEM_PUBLICA = 'TRIAGEM_PUBLICA', 'Triagem pública'
        MANUAL = 'MANUAL', 'Cadastro manual'

    cpf = EncryptedCharField('CPF', max_length=200)
    cpf_hash = models.CharField('Hash do CPF', max_length=64, unique=True, db_index=True)
    nome = models.CharField('Nome', max_length=200)
    telefone = EncryptedCharField('Telefone', max_length=200, blank=True)
    email = models.EmailField('E-mail', blank=True)
    data_nascimento = EncryptedDateField('Data de nascimento', null=True, blank=True)
    cargo = models.CharField('Cargo', max_length=120, blank=True)
    empregador = models.CharField('Empregador', max_length=200, blank=True)
    observacoes = models.TextField('Observações', blank=True)

    origem = models.CharField(
        'Origem do cadastro', max_length=20,
        choices=Origem.choices, default=Origem.MANUAL,
    )
    atualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='associados_atualizados', verbose_name='Atualizado por',
    )
    created_at = models.DateTimeField('Criado em', auto_now_add=True)
    updated_at = models.DateTimeField('Atualizado em', auto_now=True)

    class Meta:
        verbose_name = 'Associado'
        verbose_name_plural = 'Associados'
        ordering = ['nome']

    def save(self, *args, **kwargs):
        self.cpf_hash = _cpf_hash(self.cpf)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nome or f'Associado {self.pk}'

    @property
    def casos_abertos(self):
        return self.casos.exclude(status__in=[Caso.Status.ENCERRADO, Caso.Status.ARQUIVADO])

    @classmethod
    def upsert_from_atendimento(cls, at, origem):
        """Cria ou complementa a ficha a partir de um Atendimento.

        Preenche apenas campos vazios — nunca sobrescreve o que a equipe editou.
        Retorna a instância (ou None se o atendimento não tem CPF).
        """
        h = at.cpf_hash or _cpf_hash(at.cpf)
        if not h:
            return None

        nome_real = (at.nome_filiado or '').strip()
        if nome_real == NOME_PLACEHOLDER:
            nome_real = ''

        obj = cls.objects.filter(cpf_hash=h).first()
        if obj is None:
            try:
                obj = cls.objects.create(
                    cpf=at.cpf,
                    nome=nome_real or NOME_PLACEHOLDER,
                    telefone=at.telefone or '',
                    email=at.email_filiado or '',
                    origem=origem,
                )
            except IntegrityError:
                # Corrida entre requisições: outro processo criou primeiro
                obj = cls.objects.get(cpf_hash=h)
            else:
                return obj

        update_fields = []
        if nome_real and (not obj.nome or obj.nome == NOME_PLACEHOLDER):
            obj.nome = nome_real
            update_fields.append('nome')
        if at.telefone and not obj.telefone:
            obj.telefone = at.telefone
            update_fields.append('telefone')
        if at.email_filiado and not obj.email:
            obj.email = at.email_filiado
            update_fields.append('email')
        if update_fields:
            obj.save(update_fields=update_fields + ['updated_at'])
        return obj


class Caso(models.Model):
    class Tipo(models.TextChoices):
        TRABALHISTA = 'TRABALHISTA', 'Trabalhista'
        PREVIDENCIARIO = 'PREVIDENCIARIO', 'Previdenciário'
        ANDAMENTO_PROCESSO = 'ANDAMENTO_PROCESSO', 'Andamento de Processo'
        MEDICO = 'MEDICO', 'Médico do Trabalho'
        DENUNCIA = 'DENUNCIA', 'Denúncia'
        OUTRO = 'OUTRO', 'Outro'

    class Status(models.TextChoices):
        ABERTO = 'ABERTO', 'Aberto'
        EM_ANDAMENTO = 'EM_ANDAMENTO', 'Em andamento'
        AGUARDANDO_DOCUMENTOS = 'AGUARDANDO_DOCUMENTOS', 'Aguardando documentos'
        ENCERRADO = 'ENCERRADO', 'Encerrado'
        ARQUIVADO = 'ARQUIVADO', 'Arquivado'

    STATUS_COLORS = {
        'ABERTO': '#3b82f6',
        'EM_ANDAMENTO': '#f59e0b',
        'AGUARDANDO_DOCUMENTOS': '#a855f7',
        'ENCERRADO': '#22c55e',
        'ARQUIVADO': '#64748b',
    }

    associado = models.ForeignKey(
        Associado, on_delete=models.CASCADE,
        related_name='casos', verbose_name='Associado',
    )
    tipo = models.CharField('Tipo', max_length=20, choices=Tipo.choices, default=Tipo.OUTRO)
    titulo = models.CharField('Título', max_length=200)
    descricao = models.TextField('Descrição', blank=True)
    status = models.CharField('Status', max_length=25, choices=Status.choices, default=Status.ABERTO)
    departamento_responsavel = models.ForeignKey(
        'core.Department', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='casos', verbose_name='Departamento responsável',
    )
    responsavel = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='casos_responsavel', verbose_name='Responsável',
    )
    atendimentos = models.ManyToManyField(
        'atendimento.Atendimento', blank=True,
        related_name='casos', verbose_name='Atendimentos relacionados',
    )
    # Ponto de extensão (ex.: futura geração de petição — nº do processo, vara, réu…)
    dados_extra = models.JSONField('Dados adicionais', default=dict, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name='casos_criados', verbose_name='Criado por',
    )
    created_at = models.DateTimeField('Criado em', auto_now_add=True)
    updated_at = models.DateTimeField('Atualizado em', auto_now=True)
    encerrado_em = models.DateTimeField('Encerrado em', null=True, blank=True)

    class Meta:
        verbose_name = 'Caso'
        verbose_name_plural = 'Casos'
        ordering = ['-updated_at']

    def __str__(self):
        return f'{self.titulo} — {self.associado}'

    @property
    def status_color(self):
        return self.STATUS_COLORS.get(self.status, '#64748b')


class CasoDocumento(models.Model):
    class Tipo(models.TextChoices):
        DOCUMENTO_PESSOAL = 'DOCUMENTO_PESSOAL', 'Documento pessoal'
        PROCURACAO = 'PROCURACAO', 'Procuração'
        CONTRATO = 'CONTRATO', 'Contrato'
        COMPROVANTE = 'COMPROVANTE', 'Comprovante'
        EXAME = 'EXAME', 'Exame/Laudo'
        PROCESSO = 'PROCESSO', 'Peça processual'
        OUTRO = 'OUTRO', 'Outro'

    caso = models.ForeignKey(
        Caso, on_delete=models.CASCADE,
        related_name='documentos', verbose_name='Caso',
    )
    tipo = models.CharField('Tipo', max_length=20, choices=Tipo.choices, default=Tipo.OUTRO)
    arquivo = models.FileField(
        'Arquivo', upload_to='casos/%Y/%m/',
        validators=[validate_file_extension, validate_file_size],
    )
    nome_original = models.CharField('Nome do arquivo', max_length=255)
    enviado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        verbose_name='Enviado por',
    )
    created_at = models.DateTimeField('Enviado em', auto_now_add=True)

    class Meta:
        verbose_name = 'Documento do caso'
        verbose_name_plural = 'Documentos do caso'
        ordering = ['created_at']

    def __str__(self):
        return self.nome_original
