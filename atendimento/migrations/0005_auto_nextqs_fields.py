from django.db import migrations, models
import core.encryption


class Migration(migrations.Migration):

    dependencies = [
        ('atendimento', '0004_atendimento_iniciado_em'),
    ]

    operations = [
        migrations.AddField(
            model_name='atendimento',
            name='is_auto_nextqs',
            field=models.BooleanField(default=False, verbose_name='Gerado pelo NextQS'),
        ),
        migrations.AlterField(
            model_name='atendimento',
            name='cpf',
            field=core.encryption.EncryptedCharField(blank=True, max_length=200, verbose_name='CPF'),
        ),
        migrations.AlterField(
            model_name='atendimento',
            name='nome_filiado',
            field=models.CharField(blank=True, max_length=200, verbose_name='Nome do filiado'),
        ),
        migrations.AlterField(
            model_name='atendimento',
            name='assunto',
            field=models.CharField(blank=True, max_length=200, verbose_name='Assunto'),
        ),
    ]
