from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('atendimento', '0003_atendimento_is_retorno_atendimento_nextqs_fila_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='atendimento',
            name='iniciado_em',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Iniciado em'),
        ),
    ]
