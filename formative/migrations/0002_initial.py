# Generated by Django 4.0.2 on 2022-02-03 19:39

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
        ('formative', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Form',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=64)),
                ('slug', models.SlugField(allow_unicode=True, editable=False, max_length=64)),
                ('db_slug', models.SlugField(allow_unicode=True, editable=False, max_length=64)),
                ('status', models.CharField(choices=[('draft', 'unpublished'), ('disabled', 'submissions disabled'), ('enabled', 'published/enabled'), ('completed', 'completed')], default='draft', max_length=16)),
                ('options', models.JSONField(blank=True, default=dict)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ('completed', models.DateTimeField(blank=True, editable=False, null=True)),
                ('validation_type', models.CharField(choices=[('email', 'email address')], default='email', editable=False, max_length=16)),
            ],
        ),
        migrations.CreateModel(
            name='FormBlock',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('_rank', models.IntegerField(default=0, editable=False)),
                ('name', models.SlugField(allow_unicode=True, max_length=32, verbose_name='identifier')),
                ('options', models.JSONField(blank=True, default=dict)),
                ('page', models.PositiveIntegerField(default=1)),
                ('negate_dependencies', models.BooleanField(default=False, verbose_name='negate dependency')),
                ('dependence', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='dependents', related_query_name='dependent', to='formative.formblock')),
                ('form', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='blocks', related_query_name='block', to='formative.form')),
                ('polymorphic_ctype', models.ForeignKey(editable=False, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='polymorphic_%(app_label)s.%(class)s_set+', to='contenttypes.contenttype')),
            ],
            options={
                'ordering': ['form', 'page', '_rank'],
                'abstract': False,
                'base_manager_name': 'objects',
            },
        ),
        migrations.CreateModel(
            name='Program',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=32)),
                ('slug', models.SlugField(allow_unicode=True, editable=False, max_length=32, unique=True)),
                ('db_slug', models.SlugField(allow_unicode=True, editable=False, max_length=32, unique=True)),
                ('description', models.CharField(blank=True, max_length=250)),
                ('options', models.JSONField(blank=True, default=dict)),
                ('hidden', models.BooleanField(default=False)),
                ('created', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'ordering': ['created'],
            },
        ),
        migrations.CreateModel(
            name='CollectionBlock',
            fields=[
                ('block', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='formative.formblock')),
                ('fixed', models.BooleanField(default=False)),
                ('min_items', models.PositiveIntegerField(blank=True, null=True)),
                ('max_items', models.PositiveIntegerField(blank=True, null=True)),
                ('has_file', models.BooleanField(default=False)),
                ('file_optional', models.BooleanField(default=False)),
                ('name1', models.CharField(blank=True, default='', max_length=32)),
                ('name2', models.CharField(blank=True, default='', max_length=32)),
                ('name3', models.CharField(blank=True, default='', max_length=32)),
                ('align_type', models.CharField(choices=[('horizontal', 'horizontal'), ('vertical', 'vertical')], default='horizontal', max_length=16)),
            ],
            options={
                'db_table': 'formative_formcollectionblock',
            },
            bases=('formative.formblock',),
        ),
        migrations.CreateModel(
            name='CustomBlock',
            fields=[
                ('block', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='formative.formblock')),
                ('type', models.CharField(choices=[('text', 'text'), ('num', 'numeric'), ('choice', 'multiple choice'), ('bool', 'true/false choice')], default='text', max_length=16)),
                ('required', models.BooleanField(default=False)),
                ('num_lines', models.PositiveIntegerField(default=1)),
                ('min_chars', models.PositiveIntegerField(blank=True, null=True)),
                ('max_chars', models.PositiveIntegerField(blank=True, null=True)),
                ('min_words', models.PositiveIntegerField(blank=True, null=True)),
                ('max_words', models.PositiveIntegerField(blank=True, null=True)),
            ],
            options={
                'db_table': 'formative_formcustomblock',
            },
            bases=('formative.formblock',),
        ),
        migrations.CreateModel(
            name='FormLabel',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('path', models.CharField(max_length=128)),
                ('text', models.CharField(max_length=1000)),
                ('style', models.CharField(choices=[('widget', 'widget label'), ('vertical', 'vertical label'), ('horizontal', 'horizontal label')], default='widget', max_length=16)),
                ('form', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='labels', related_query_name='label', to='formative.form')),
            ],
        ),
        migrations.CreateModel(
            name='FormDependency',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('value', models.CharField(blank=True, max_length=64)),
                ('block', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='dependencies', related_query_name='dependency', to='formative.formblock')),
            ],
            options={
                'verbose_name': 'dependency value',
                'verbose_name_plural': 'dependency values',
            },
        ),
        migrations.AddField(
            model_name='form',
            name='program',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='forms', related_query_name='form', to='formative.program'),
        ),
        migrations.AddConstraint(
            model_name='formlabel',
            constraint=models.UniqueConstraint(fields=('form', 'path', 'style'), name='unique_path_style'),
        ),
        migrations.AddConstraint(
            model_name='formdependency',
            constraint=models.UniqueConstraint(fields=('block', 'value'), name='unique_blockval'),
        ),
        migrations.AddConstraint(
            model_name='formblock',
            constraint=models.UniqueConstraint(fields=('form', 'page', '_rank'), name='unique_rank'),
        ),
        migrations.AddConstraint(
            model_name='form',
            constraint=models.UniqueConstraint(fields=('program', 'slug'), name='unique_slug'),
        ),
        migrations.AddConstraint(
            model_name='form',
            constraint=models.UniqueConstraint(fields=('program', 'db_slug'), name='unique_db_slug'),
        ),
    ]
