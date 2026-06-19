from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('atendimento', '0005_auto_nextqs_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='atendimento',
            name='is_preferencial',
            field=models.BooleanField(default=False, verbose_name='Atendimento preferencial'),
        ),
    ]
