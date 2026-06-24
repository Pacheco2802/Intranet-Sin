# Reembolso: papel_assinado/comprovante fixos → anexos genéricos múltiplos.

import core.validators
import django.db.models.deletion
from django.db import migrations, models


def migrar_para_anexos(apps, schema_editor):
    """Move os arquivos já enviados (papel_assinado e comprovante) para a nova
    tabela de anexos, para não perder nada do que já existe em produção."""
    Reembolso = apps.get_model('financeiro', 'Reembolso')
    ReembolsoAnexo = apps.get_model('financeiro', 'ReembolsoAnexo')
    for r in Reembolso.objects.all():
        for campo in ('papel_assinado', 'comprovante'):
            arquivo = getattr(r, campo, None)
            if arquivo:
                ReembolsoAnexo.objects.create(reembolso=r, arquivo=arquivo.name)


def reverter(apps, schema_editor):
    """Sem reversão de dados: os campos antigos são recriados vazios pela
    operação inversa de RemoveField."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('financeiro', '0005_atividadediretoria_motivo_ajuste'),
    ]

    operations = [
        migrations.CreateModel(
            name='ReembolsoAnexo',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('arquivo', models.FileField(upload_to='financeiro/reembolsos/%Y/%m/', validators=[core.validators.validate_file_extension, core.validators.validate_file_size], verbose_name='Arquivo')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('reembolso', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='anexos', to='financeiro.reembolso', verbose_name='Reembolso')),
            ],
            options={
                'verbose_name': 'Anexo de Reembolso',
                'verbose_name_plural': 'Anexos de Reembolso',
                'ordering': ['created_at'],
            },
        ),
        migrations.RunPython(migrar_para_anexos, reverter),
        migrations.RemoveField(
            model_name='reembolso',
            name='papel_assinado',
        ),
        migrations.RemoveField(
            model_name='reembolso',
            name='comprovante',
        ),
    ]
