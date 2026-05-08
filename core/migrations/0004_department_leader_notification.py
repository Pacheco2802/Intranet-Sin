from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_team_conversation_team_is_protected'),
    ]

    operations = [
        migrations.AddField(
            model_name='department',
            name='leader',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='led_departments',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Líder',
            ),
        ),
        migrations.CreateModel(
            name='Notification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('type', models.CharField(
                    choices=[
                        ('CARD_ASSIGNED', 'Card atribuído a você'),
                        ('CARD_DEPT', 'Card criado na sua área'),
                        ('CARD_CROSS', 'Card entre departamentos'),
                    ],
                    max_length=20, verbose_name='Tipo',
                )),
                ('title', models.CharField(max_length=200, verbose_name='Título')),
                ('body', models.TextField(blank=True, verbose_name='Mensagem')),
                ('link', models.CharField(blank=True, max_length=500, verbose_name='Link')),
                ('is_read', models.BooleanField(default=False, verbose_name='Lida')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('actor', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='sent_notifications',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Quem gerou',
                )),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='notifications',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Destinatário',
                )),
            ],
            options={
                'verbose_name': 'Notificação',
                'verbose_name_plural': 'Notificações',
                'ordering': ['-created_at'],
            },
        ),
    ]
