import core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('consultas', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name='consulta',
            name='status',
            field=models.CharField(
                choices=[
                    ('agendado',   'Agendado'),
                    ('confirmado', 'Confirmado'),
                    ('presente',   'Presente'),
                    ('faltou',     'Faltou'),
                    ('cancelado',  'Cancelado'),
                    ('remarcado',  'Remarcado'),
                    ('finalizado', 'Finalizado'),
                ],
                default='agendado', max_length=12, verbose_name='Status',
            ),
        ),
        migrations.CreateModel(
            name='Atendimento',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('pressao_arterial', models.CharField(blank=True, max_length=10, verbose_name='Pressão arterial')),
                ('peso', models.DecimalField(blank=True, decimal_places=1, max_digits=5, null=True, verbose_name='Peso (kg)')),
                ('altura', models.DecimalField(blank=True, decimal_places=2, max_digits=4, null=True, verbose_name='Altura (m)')),
                ('queixa_principal', models.TextField(blank=True, verbose_name='Queixa principal')),
                ('anamnese', models.TextField(blank=True, verbose_name='Anamnese / Histórico')),
                ('exame_clinico', models.TextField(blank=True, verbose_name='Exame clínico')),
                ('diagnostico', models.TextField(blank=True, verbose_name='Diagnóstico / Impressão')),
                ('cid', models.CharField(blank=True, max_length=10, verbose_name='CID-10')),
                ('conduta', models.TextField(blank=True, verbose_name='Conduta')),
                ('finalizado', models.BooleanField(default=False, verbose_name='Finalizado')),
                ('finalizado_em', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('consulta', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='atendimento',
                    to='consultas.consulta',
                    verbose_name='Consulta',
                )),
                ('finalizado_por', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='atendimentos_finalizados',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Prontuário',
                'verbose_name_plural': 'Prontuários',
            },
        ),
        migrations.CreateModel(
            name='ConsultaDocumento',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tipo', models.CharField(
                    choices=[
                        ('exame',          'Exame / Laudo'),
                        ('receita',        'Receita'),
                        ('atestado',       'Atestado'),
                        ('encaminhamento', 'Encaminhamento'),
                        ('outro',          'Outro'),
                    ],
                    default='outro', max_length=20, verbose_name='Tipo',
                )),
                ('titulo', models.CharField(max_length=200, verbose_name='Título')),
                ('arquivo', models.FileField(
                    upload_to='consultas/%Y/%m/',
                    validators=[core.validators.validate_file_extension, core.validators.validate_file_size],
                    verbose_name='Arquivo',
                )),
                ('nome_original', models.CharField(max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('consulta', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='documentos',
                    to='consultas.consulta',
                    verbose_name='Consulta',
                )),
                ('enviado_por', models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='documentos_consulta',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Documento',
                'verbose_name_plural': 'Documentos',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='ASO',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tipo_exame', models.CharField(
                    choices=[
                        ('admissional',    'Admissional'),
                        ('periodico',      'Periódico'),
                        ('retorno',        'Retorno ao Trabalho'),
                        ('mudanca_funcao', 'Mudança de Função'),
                        ('demissional',    'Demissional'),
                    ],
                    max_length=20, verbose_name='Tipo de exame',
                )),
                ('resultado', models.CharField(
                    choices=[
                        ('apto',           'Apto'),
                        ('apto_restricao', 'Apto com Restrição'),
                        ('inapto',         'Inapto'),
                    ],
                    max_length=15, verbose_name='Resultado',
                )),
                ('restricoes', models.TextField(blank=True, verbose_name='Restrições')),
                ('riscos_ocupacionais', models.TextField(blank=True, verbose_name='Riscos ocupacionais')),
                ('exames_realizados', models.TextField(blank=True, verbose_name='Exames realizados')),
                ('cid', models.CharField(blank=True, max_length=10, verbose_name='CID-10')),
                ('validade_dias', models.SmallIntegerField(default=365, verbose_name='Validade (dias)')),
                ('data_emissao', models.DateField(auto_now_add=True, verbose_name='Data de emissão')),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('consulta', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='aso',
                    to='consultas.consulta',
                    verbose_name='Consulta',
                )),
                ('created_by', models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='asos_emitidos',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'ASO',
                'verbose_name_plural': 'ASOs',
            },
        ),
    ]
