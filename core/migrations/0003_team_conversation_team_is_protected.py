from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_team_customuser_email_unique_customuser_is_approved'),
        ('mensagens', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='team',
            name='is_protected',
            field=models.BooleanField(default=False, verbose_name='Protegida'),
        ),
        migrations.AddField(
            model_name='team',
            name='conversation',
            field=models.OneToOneField(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='team',
                to='mensagens.conversation',
                verbose_name='Chat da equipe',
            ),
        ),
    ]
