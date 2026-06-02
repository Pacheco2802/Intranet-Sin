from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Doctor',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name',   models.CharField(max_length=100, verbose_name='Nome')),
                ('room',   models.CharField(blank=True, max_length=50, verbose_name='Sala')),
                ('color',  models.CharField(default='#1e3a5f', max_length=7, verbose_name='Cor')),
                ('active', models.BooleanField(default=True, verbose_name='Ativo')),
                ('order',  models.SmallIntegerField(default=0, verbose_name='Ordem')),
                ('user',   models.OneToOneField(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='doctor_profile',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Usuário vinculado',
                )),
            ],
            options={
                'verbose_name': 'Médico',
                'verbose_name_plural': 'Médicos',
                'ordering': ['order', 'name'],
            },
        ),
        migrations.CreateModel(
            name='Consulta',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('patient_name',     models.CharField(max_length=200, verbose_name='Nome do paciente')),
                ('patient_cpf',      models.CharField(blank=True, max_length=20, verbose_name='CPF')),
                ('patient_phone',    models.CharField(blank=True, max_length=30, verbose_name='Telefone')),
                ('date',             models.DateField(verbose_name='Data')),
                ('time',             models.TimeField(verbose_name='Horário')),
                ('duration_minutes', models.SmallIntegerField(default=30, verbose_name='Duração (min)')),
                ('status',           models.CharField(
                    choices=[
                        ('agendado',   'Agendado'),
                        ('confirmado', 'Confirmado'),
                        ('presente',   'Presente'),
                        ('faltou',     'Faltou'),
                        ('cancelado',  'Cancelado'),
                        ('remarcado',  'Remarcado'),
                    ],
                    default='agendado', max_length=12, verbose_name='Status',
                )),
                ('notes',      models.TextField(blank=True, verbose_name='Observações')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('doctor', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='consultas',
                    to='consultas.doctor',
                    verbose_name='Médico',
                )),
                ('rescheduled_to', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='rescheduled_from',
                    to='consultas.consulta',
                    verbose_name='Remarcada para',
                )),
                ('created_by', models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='consultas_criadas',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Criado por',
                )),
            ],
            options={
                'verbose_name': 'Consulta',
                'verbose_name_plural': 'Consultas',
                'ordering': ['date', 'time'],
            },
        ),
    ]
