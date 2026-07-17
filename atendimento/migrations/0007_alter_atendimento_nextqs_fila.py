from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('atendimento', '0006_atendimento_is_preferencial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='atendimento',
            name='nextqs_fila',
            field=models.CharField(
                blank=True,
                choices=[
                    ('J', 'Jurídico'),
                    ('P', 'Previdenciário'),
                    ('T', 'Trabalhista'),
                    ('A', 'Andamento de Processo'),
                    ('M', 'Médico do Trabalho'),
                    ('D', 'Denúncia'),
                ],
                max_length=1,
                verbose_name='Fila NextQS',
            ),
        ),
    ]
