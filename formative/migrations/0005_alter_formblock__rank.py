# Generated by Django 4.0.2 on 2022-03-03 19:11

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('formative', '0004_alter_form_db_slug_alter_form_slug_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='formblock',
            name='_rank',
            field=models.IntegerField(default=0, null=True, verbose_name=''),
        ),
    ]
