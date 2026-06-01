from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0012_user_can_post_comunicado'),
    ]

    operations = [
        migrations.AlterField(
            model_name='customuser',
            name='role',
            field=models.CharField(
                choices=[
                    ('PRESIDENTE', 'Presidente'),
                    ('COORD_GERAL', 'Coord. Geral'),
                    ('DIRETOR', 'Diretor'),
                    ('ADMIN_TI', 'Administrador TI'),
                    ('LIDER', 'Líder'),
                    ('COLABORADOR', 'Colaborador'),
                ],
                default='COLABORADOR',
                max_length=20,
                verbose_name='Cargo',
            ),
        ),
    ]
