# Generated by Django 4.0.4 on 2022-05-13 19:39

from django.db import migrations, models
import django.db.models.deletion

def set_usernames(apps, schema_editor):
    User = apps.get_model('formative', 'User')
    User.objects.filter(is_superuser=False).update(username=models.F('email'))

def nop(apps, schema_editor): pass


class Migration(migrations.Migration):

    dependencies = [
        ('formative', '0009_custom_user_model'),
    ]

    operations = [
        migrations.AlterField(
            model_name='site',
            name='time_zone',
            field=models.CharField(blank=True, max_length=32),
        ),
        migrations.AlterModelOptions(
            name='user',
            options={'ordering': ['site', 'email']},
        ),
        migrations.AddField(
            model_name='user',
            name='site',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='users', related_query_name='user', to='formative.site'),
        ),
        migrations.AddField(
            model_name='user',
            name='programs',
            field=models.ManyToManyField(blank=True, related_name='users', related_query_name='user', to='formative.program'),
        ),
        migrations.AddConstraint(
            model_name='user',
            constraint=models.UniqueConstraint(fields=('site', 'email'), name='uniq_site_email'),
        ),
        migrations.AlterModelTable(
            name='user',
            table=None,
        ),
        migrations.RunPython(set_usernames, nop)
    ]
