from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('kanban', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='board',
            name='is_global',
            field=models.BooleanField(default=False, verbose_name='Board Geral'),
        ),
        migrations.AddField(
            model_name='board',
            name='is_auto',
            field=models.BooleanField(default=False, verbose_name='Criado automaticamente'),
        ),
    ]
