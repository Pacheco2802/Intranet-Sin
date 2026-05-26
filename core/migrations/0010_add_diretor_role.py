from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0009_customuser_nextqs_agent_id_alter_notification_type'),
    ]

    operations = [
        migrations.AlterField(
            model_name='customuser',
            name='role',
            field=models.CharField(
                choices=[
                    ('PRESIDENTE', 'Presidente'),
                    ('DIRETOR', 'Diretor'),
                    ('ADMIN_TI', 'Administrador TI'),
                    ('LIDER', 'Líder'),
                    ('GERENTE', 'Gerente'),
                    ('COLABORADOR', 'Colaborador'),
                ],
                default='COLABORADOR',
                max_length=20,
                verbose_name='Cargo',
            ),
        ),
    ]
