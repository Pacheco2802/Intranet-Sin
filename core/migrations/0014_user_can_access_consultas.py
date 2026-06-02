from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0013_add_coord_geral_role'),
    ]

    operations = [
        migrations.AddField(
            model_name='customuser',
            name='can_access_consultas',
            field=models.BooleanField(default=False, verbose_name='Acesso à Agenda Médica'),
        ),
    ]
