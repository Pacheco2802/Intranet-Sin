from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='customuser',
            name='is_approved',
            field=models.BooleanField(default=False, verbose_name='Aprovado'),
        ),
        migrations.AlterField(
            model_name='customuser',
            name='email',
            field=models.EmailField(max_length=254, unique=True, verbose_name='E-mail'),
        ),
        migrations.CreateModel(
            name='Team',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, verbose_name='Nome')),
                ('is_general', models.BooleanField(default=False, verbose_name='Equipe Geral')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('department', models.OneToOneField(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='team',
                    to='core.department',
                    verbose_name='Departamento',
                )),
                ('members', models.ManyToManyField(
                    blank=True,
                    related_name='teams',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Membros',
                )),
            ],
            options={
                'verbose_name': 'Equipe',
                'verbose_name_plural': 'Equipes',
                'ordering': ['-is_general', 'name'],
            },
        ),
    ]
