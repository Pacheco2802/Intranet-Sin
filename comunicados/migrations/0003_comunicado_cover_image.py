from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('comunicados', '0002_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='comunicado',
            name='cover_image',
            field=models.ImageField(blank=True, null=True, upload_to='comunicados/', verbose_name='Imagem de capa'),
        ),
    ]
