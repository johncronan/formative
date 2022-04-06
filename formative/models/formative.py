from django.db import models, connection
from django.db.models import Q, Max, Case, Value, When, Exists, OuterRef, \
    UniqueConstraint, Subquery
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.core.exceptions import FieldError, ValidationError
from django.template import Template, loader
from django.utils.functional import cached_property
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.urls import reverse
from polymorphic.models import PolymorphicModel
import uuid
from itertools import groupby
from pathlib import Path
from datetime import timedelta
import os

from ..stock import StockWidget
from ..filetype import FileType
from ..utils import create_model, remove_p, send_email, submission_link, \
    thumbnail_path, MarkdownFormatter
from .ranked import RankedModel, UnderscoredRankedModel
from .automatic import AutoSlugModel


markdown = MarkdownFormatter()


class Program(AutoSlugModel):
    class Meta:
        ordering = ['created']
    
    name = models.CharField(max_length=64)
    slug = models.SlugField(max_length=30, unique=True, allow_unicode=True,
                            verbose_name='identifier')
    db_slug = models.SlugField(max_length=30, unique=True, allow_unicode=True,
                               editable=False)
    description = models.CharField(max_length=250, blank=True)
    options = models.JSONField(default=dict, blank=True)
    hidden = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
    
    def validate_unique(self, exclude=None):
        super().validate_unique(exclude=exclude)
        if not self._state.adding: return
        
        if Program.objects.filter(db_slug=self.slug.replace('-', '')).exists():
            msg = 'Identifier (with hyphens removed) must be unique.'
            raise ValidationError(msg)
    
    def visible_forms(self):
        pub = self.forms.exclude(status=Form.Status.DRAFT)
        return pub.exclude(options__hidden__isnull=False)
    
    def home_url(self):
        if 'home_url' in self.options: return self.options['home_url']
        return None


class Form(AutoSlugModel):
    class Meta:
        constraints = [
            UniqueConstraint(fields=['program', 'slug'], name='unique_slug'),
            UniqueConstraint(fields=['program', 'db_slug'],
                             name='unique_db_slug')
        ]
    
    class Status(models.TextChoices):
        DRAFT = 'draft', _('unpublished')
        DISABLED = 'disabled', _('submissions disabled')
        ENABLED = 'enabled', _('published/enabled')
        COMPLETED = 'completed', _('completed')
    
    class Validation(models.TextChoices):
        # currently, validation to create a submission is always by email
        EMAIL = 'email', _('email address')
    
    program = models.ForeignKey(Program, models.CASCADE,
                                related_name='forms', related_query_name='form')
    name = models.CharField(max_length=64)
    slug = models.SlugField(max_length=30, allow_unicode=True,
                            verbose_name='identifier')
    db_slug = models.SlugField(max_length=30, allow_unicode=True,
                               editable=False)
    status = models.CharField(max_length=16, default=Status.DRAFT,
                              choices=Status.choices)
    options = models.JSONField(default=dict, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    # this is also the published date, for enabled and completed forms
    modified = models.DateTimeField(default=timezone.now, editable=False)
    completed = models.DateTimeField(null=True, blank=True, editable=False)
    validation_type = models.CharField(max_length=16, editable=False,
                                       default=Validation.EMAIL,
                                       choices=Validation.choices)
    
    def __str__(self):
        return self.name
    
    def validate_unique(self, exclude=None):
        super().validate_unique(exclude=exclude)
        if not self._state.adding: return
        
        if Form.objects.filter(program=self.program,
                               db_slug=self.slug.replace('-', '')).exists():
            msg = 'Identifier (with hyphens removed) must be unique ' \
                  'within this program.'
            raise ValidationError(msg)
    
    @cached_property
    def model(self):
        if self.status == self.Status.DRAFT: return None
        
        fields = []
        for block in self.blocks.exclude(page=0, _rank__gt=1):
            fields += block.fields()
        
        name = self.program.db_slug + '_' + self.db_slug
        class Meta:
            verbose_name = self.slug + ' submission'
            verbose_name_plural = self.slug + ' submissions'
        return create_model(name, fields, program=self.program.db_slug,
                            base_class=Submission, meta=Meta)
    
    @cached_property
    def item_model(self):
        if self.status == self.Status.DRAFT: return None
        
        collections = self.collections()
        if not collections: return None
        
        names = []
        for c in collections:
            for field in c.collection_fields():
                if field not in names: names.append(field)
        
        fields = [
            # the first column links submission items to the submission
            ('_submission', models.ForeignKey(self.model, models.CASCADE,
                                              related_name='_items',
                                              related_query_name='_item'))
        ]
        
        field_blocks = { b.name: b for b in
                         self.custom_blocks().filter(page=0, _rank__gt=1) }
        for n in names:
            # look for a CustomBlock with the same name on page 0 (hidden)
            if n in field_blocks: block = field_blocks[n]
            # otherwise, use the default text CustomBlock
            else: block = CustomBlock.text_create()
            fields.append((n, block.field()))
        
        name = self.program.db_slug + '_' + self.db_slug + '_i'
        class Meta:
            constraints = [
                UniqueConstraint(
                    fields=['_submission', '_collection', '_block', '_rank'],
                    name=self.program.db_slug+'_'+self.db_slug+'_u'
                )
            ]
            verbose_name = self.slug + ' item'
            verbose_name_plural = self.slug + ' items'
        return create_model(name, fields, program=self.program.db_slug,
                            base_class=SubmissionItem, meta=Meta)
    
    def cache_dirty(self):
        version = cache.get('models_version')
        if version is None: cache.set('models_version', 1, timeout=None)
        else: cache.incr('models_version')
    
    def publish_model(self, model, admin=None):
        with connection.schema_editor() as editor:
            editor.create_model(model)
        ctype = ContentType(app_label=model._meta.app_label,
                            model=model.__name__)
        ctype.save()
        ContentType.objects.clear_cache()
        
        self.cache_dirty()
    
    def unpublish_model(self, model):
        self.cache_dirty()
        
        ctype = ContentType.objects.get_for_model(model)
        ctype.delete()
        ContentType.objects.clear_cache()
        with connection.schema_editor() as editor:
            editor.delete_model(model)
    
    def publish(self):
        if self.status != self.Status.DRAFT: return
        
        self.status = self.Status.ENABLED
        if 'model' in self.__dict__: del self.model
        if 'item_model' in self.__dict__: del self.item_model
        
        from ..admin import SubmissionAdmin, SubmissionItemAdmin
        self.publish_model(self.model, admin=SubmissionAdmin)
        if self.item_model:
            self.publish_model(self.item_model, admin=SubmissionItemAdmin)
        
        self.modified = timezone.now()
        self.save()
    
    def unpublish(self):
        if self.status == self.Status.DRAFT: return
        
        rec_type = SubmissionRecord.RecordType.SUBMISSION
        recs = SubmissionRecord.objects.filter(program=self.program,
                                               form=self.slug, type=rec_type)
        recs.update(deleted=True)
        
        self.unpublish_model(self.model)
        if self.item_model: self.unpublish_model(self.item_model)
        
        self.status = self.Status.DRAFT
        if 'model' in self.__dict__: del self.model
        if 'item_model' in self.__dict__: del self.item_model
        
        self.modified, self.completed = timezone.now(), None
        self.save()
    
    def get_available_plugins(self):
        from ..plugins import get_all_plugins
        
        return { plugin.module: plugin for plugin in get_all_plugins(self)
                 if not plugin.name.startswith('.') }
    
    def get_plugins(self):
        if 'plugins' in self.options: return self.options['plugins']
        return []
    
    def add_plugins(self, plugins):
        available = self.get_available_plugins()
        
        enable = [ p for p in plugins if p in available ]
        for plugin in enable:
            if hasattr(available[plugin].app, 'installed'):
                getattr(available[plugin].app, 'installed')(self)
        
        if 'plugins' not in self.options: self.options['plugins'] = []
        self.options['plugins'] += plugins
    
    def remove_plugins(self, plugins):
        available = self.get_available_plugins()

        for plugin in plugins:
            if hasattr(available[plugin].app, 'uninstalled'):
                getattr(available[plugin].app, 'uninstalled')(self)

        new_plugins = [ p for p in self.options['plugins'] if p not in plugins ]
        self.options['plugins'] = new_plugins
    
    def default_text_label_style(self):
        if 'default_text_label_style' in self.options:
            return self.options['default_text_label_style']
        return FormLabel.LabelStyle.WIDGET
    
    def num_pages(self):
        return self.blocks.aggregate(Max('page'))['page__max']
    
    def custom_blocks(self):
        return CustomBlock.objects.filter(form=self).non_polymorphic()
    
    def submission_blocks(self):
        blocks = self.blocks.not_instance_of(CollectionBlock)
        return blocks.exclude(page=0, _rank__gt=0)
    
    def collections(self, name=None):
        blocks = CollectionBlock.objects.filter(form=self)
        if name: return blocks.filter(name=name).non_polymorphic()
        return blocks.non_polymorphic()
    
    def validation_block(self):
        return self.blocks.get(page=0, _rank=1)
    
    def visible_blocks(self, page=None, skip=None):
        query = self.blocks.all()
        if skip: query = query.exclude(id__in=skip)
        if page and page > 0: return query.filter(page=page)
        else: return query.exclude(page=0, _rank__gt=0)
        return query.filter(page__gt=0)
    
    def visible_items(self, submission, page=None, skip=None):
        if not self.item_model: return []
        
        query = self.item_model.objects.filter(_submission=submission)
        if skip: query = query.exclude(_block__in=skip)
        if page and page > 0:
            block_ids = Subquery(self.blocks.filter(page=page).values('pk'))
            query = query.filter(_block__in=block_ids)
        
        query = query.exclude(_file='', _filesize__gt=0) # upload in progress
        return query.order_by('_collection', '_block', '_rank')

    def field_labels(self):
        labels = {}
        for label in self.labels.all():
            key, target = label.path, labels
            if '.' in label.path:
                base, key = label.path.split('.')
                if key[-1] == '_': base, key = base + '_', key[:-1]
                
                if base not in labels: labels[base] = {}
                target = labels[base]
            if key not in target: target[key] = {}
            target[key][label.style] = label

        return labels

    def label_class(self):
        return FormLabel
    
    def status_message(self):
        if self.status == self.Status.DRAFT:
            return 'NA'
        elif self.status == self.Status.DISABLED:
            return _('Not yet open for submissions')
        elif self.status == self.Status.COMPLETED:
            return _('Closed')
        return _('Open for submissions')
    
    def hidden(self):
        return self.status != self.Status.ENABLED or 'hidden' in self.options
    
    def access_enable(self):
        if 'access_enable' in self.options: return self.options['access_enable']
        return None
    
    def timed_completion(self):
        if 'timed_completion' in self.options:
            return self.options['timed_completion']
        return None
    
    def complete_submit_time(self):
        if 'complete_submit_time' in self.options:
            return self.options['complete_submit_time']
        return 5 # minutes
    
    def extra_time(self):
        extra = self.complete_submit_time()
        if timezone.now() - self.completed <= timedelta(minutes=extra):
            return True
        return False
    
    def review_pre(self, prefix=''):
        name = prefix + 'review_pre'
        if name in self.options:
            return mark_safe(markdown.convert(self.options[name]))
        return ''
    
    def review_post(self):
        if 'review_post' in self.options:
            return mark_safe(markdown.convert(self.options['review_post']))
        return ''
    
    def submit_submission(self, submission):
        submission._submit()
        
        rec, created = SubmissionRecord.objects.get_or_create(
            program=self.program, form=self.slug, submission=submission._id,
            type=SubmissionRecord.RecordType.SUBMISSION
        )
        rec.text = submission._email
        rec.save()
        
        if self.item_model:
            dir = os.path.join(settings.MEDIA_ROOT, str(submission._id))
            if os.path.isdir(dir):
                Path(os.path.join(dir, 'submitted')).touch()
    
    def submitted_review_pre(self):
        return self.review_pre(prefix='submitted_')
    
    def review_after_submit(self):
        return 'no_review_after_submit' not in self.options
    
    def submit_button_label(self):
        if 'submit_button_label' in self.options:
            return self.options['submit_button_label']
        return 'submit'
    
    def thanks(self):
        if 'thanks' in self.options:
            return mark_safe(markdown.convert(self.options['thanks']))
    
    def emails(self):
        if 'emails' in self.options: return self.options['emails']
        return {}
    
    def email_names(self):
        names = list(self.emails())
        for name in ('confirmation', 'continue'):
            if name not in names: names.insert(0, name)
        return names
    
    def load_email_templates(self, n):
        subject = loader.get_template('formative/emails/' + n + '_subject.html')
        content = loader.get_template('formative/emails/' + n + '.html')
        return subject, content
    
    def email_templates(self):
        emails = self.emails()
        for name in ('continue', 'confirmation'):
            if name in emails: continue
            subject, content = self.load_email_templates(name)
            
            emails[name] = {'content': content.template.source,
                            'subject': subject.template.source.rstrip('\n')}
        return emails


class FormLabel(models.Model):
    class Meta:
        constraints = [
            UniqueConstraint(fields=['form', 'path', 'style'],
                             name='unique_path_style')
        ]
    
    class LabelStyle(models.TextChoices):
        WIDGET = 'widget', _('widget label')
        VERTICAL = 'vertical', _('vertical label')
        HORIZONTAL = 'horizontal', _('horizontal label')
    
    form = models.ForeignKey('Form', models.CASCADE, related_name='labels',
                             related_query_name='label')
    path = models.CharField(max_length=128)
    text = models.CharField(max_length=1000)
    style = models.CharField(max_length=16, choices=LabelStyle.choices,
                             default=LabelStyle.WIDGET)
    
    def __str__(self):
        return self.path
    
    def display(self, inline=False):
        s = markdown.convert(self.text)
        if inline: return mark_safe(remove_p(s))
        return mark_safe(s)
    
    def display_inline(self):
        return self.display(inline=True)


class FormDependency(models.Model):
    class Meta:
        verbose_name = 'dependency value'
        verbose_name_plural = 'dependency values'
        constraints = [
            UniqueConstraint(fields=['block', 'value'], name='unique_blockval')
        ]
    
    block = models.ForeignKey('FormBlock', models.CASCADE,
                              related_name='dependencies',
                              related_query_name='dependency')
    value = models.CharField(max_length=64, blank=True)
    
    def __str__(self):
        if self.block.dependence:
            return f'{self.block.dependence.name}="{self.value}"'
        return f'?="{self.value}"'


class FormBlock(PolymorphicModel, RankedModel):
    class Meta(PolymorphicModel.Meta, RankedModel.Meta):
        constraints = [
            UniqueConstraint(fields=['form', 'page', '_rank'],
                             name='unique_rank'),
        ]
        ordering = ['form', 'page', '_rank']
    
    form = models.ForeignKey(Form, models.CASCADE,
                             related_name='blocks', related_query_name='block')
    name = models.SlugField(max_length=32, verbose_name='identifier',
                            allow_unicode=True)
    options = models.JSONField(default=dict, blank=True)
    page = models.PositiveIntegerField(default=1)
    dependence = models.ForeignKey('FormBlock', models.CASCADE,
                                   null=True, blank=True,
                                   related_name='dependents',
                                   related_query_name='dependent')
    negate_dependencies = models.BooleanField(default=False,
                                              verbose_name='negate dependency')
    
    def __str__(self):
        return self.name
    
    def rank_group(self):
        return FormBlock.objects.filter(form=self.form, page=self.page)
    
    def validate_unique(self, exclude=None):
        super().validate_unique(exclude=exclude)
        if not self._state.adding: return
        
        if self.name == 'email' and self.page:
            raise ValidationError('There is already a block called "email."')
        
        # name of a collection block identifies its "bucket", not its field(s)
        # in this case, it's not required to be unique
        if self.block_type() == 'collection': return
        
        qs = FormBlock.objects.filter(form_id=self.form_id)
        if self.page: qs = qs.filter(page__gt=0)
        else: qs = qs.filter(page=0)
        if qs.filter(name=self.name).exists():
            msg = 'Identifiers for stock and custom blocks must be unique.'
            raise ValidationError(msg)
    
    def block_type(self):
        if type(self) == CustomBlock: return 'custom'
        if type(self) == CollectionBlock: return 'collection'
        return 'stock'
    
    def stock_type(self):
        if 'type' not in self.options:
            raise FieldError('untyped stock widget')
        
        return StockWidget.by_type(self.options['type'])
    
    @cached_property
    def stock(self):
        return self.stock_type()(self.name, **self.options)
    
    def fields(self):
        return self.stock.fields()
    
    def enabled_blocks(self, value, page=None):
        # blocks on the given page that depend on self, and enabled given value
        query = self.form.blocks.filter(dependence_id=self.id)
        if page: query = query.filter(page=page)
        
        if type(value) == bool: value = value and 'yes' or 'no' # TODO: numeric
        if value is None: value = ''
        
        val = FormDependency.objects.filter(block_id=OuterRef('id'),
                                            value=Value(value))
        cond = Case(
            When(negate_dependencies=False, then=Exists(val)),
            When(negate_dependencies=True, then=~Exists(val))
        )
        query = query.annotate(en=cond).filter(en=True)
        return query.values_list('id', flat=True)
    
    def min_allowed_page(self):
        min_page = 1
        
        if self.dependence: min_page = self.dependence.page + 1
        return min_page
    
    def max_allowed_page(self, last_page=None):
        if last_page is None:
            last_page = self.form.blocks.aggregate(p=Max('page'))['p'] or 1
        max_page = last_page
        
        for block in self.dependents.all():
            if block.page - 1 < max_page: max_page = block.page - 1
        return max_page
    
    def show_in_review(self):
        return 'no_review' not in self.options


class CustomBlock(FormBlock):
    class Meta:
        db_table = 'formative_formcustomblock'
    
    CHOICE_VAL_MAXLEN = 64
    DEFAULT_TEXT_MAXLEN = 1000
    MAX_TEXT_MAXLEN = 65535
    
    class InputType(models.TextChoices):
        TEXT = 'text', _('text')
        NUMERIC = 'num', _('numeric')
        CHOICE = 'choice', _('multiple choice')
        BOOLEAN = 'bool', _('true/false choice')
    
    block = models.OneToOneField(FormBlock, on_delete=models.CASCADE,
                                 parent_link=True, primary_key=True)
    type = models.CharField(max_length=16, choices=InputType.choices,
                            default=InputType.TEXT)
    required = models.BooleanField(default=False)
    num_lines = models.PositiveIntegerField(default=1)
    min_chars = models.PositiveIntegerField(null=True, blank=True)
    max_chars = models.PositiveIntegerField(null=True, blank=True)
    min_words = models.PositiveIntegerField(null=True, blank=True)
    max_words = models.PositiveIntegerField(null=True, blank=True)
    
    @classmethod
    def text_create(cls, *args, **kwargs):
        if 'max_chars' not in kwargs:
            kwargs['max_chars'] = cls.DEFAULT_TEXT_MAXLEN
        return cls(*args, **kwargs, type=cls.InputType.TEXT)
    
    def choices(self):
        if 'choices' not in self.options or not self.options['choices']:
            raise FieldError('choices not defined')
        
        return self.options['choices']
    
    def field(self):
        # fields are NULL when we haven't yet reached the page, or if their
        # block had a dependency that wasn't met. non-required fields may
        # have a different way to record that no input was made, usually ''
        if self.type == self.InputType.TEXT:
            blank, max_chars = False, self.max_chars
            
            if not self.min_chars and not self.min_words: blank = True
            if not self.max_chars or self.max_chars > self.MAX_TEXT_MAXLEN:
                max_chars = self.MAX_TEXT_MAXLEN
            
            if self.num_lines > 1 or max_chars > self.DEFAULT_TEXT_MAXLEN:
                return models.TextField(null=True, max_length=max_chars,
                                        blank=blank)
            return models.CharField(null=True, max_length=self.max_chars,
                                    blank=blank)

        elif self.type == self.InputType.NUMERIC:
            return models.IntegerField(null=True, blank=(not self.required))

        elif self.type == self.InputType.CHOICE:
            return models.CharField(null=True, blank=(not self.required),
                                    max_length=self.CHOICE_VAL_MAXLEN,
                                    choices=[(c, c) for c in self.choices()])
        
        elif self.type == self.InputType.BOOLEAN:
            return models.BooleanField(null=True)
    
    def fields(self):
        return [(self.name, self.field())]

    def form_field(self, model_field, **kwargs):
        if self.type == self.InputType.TEXT:
            return model_field.formfield(min_length=self.min_chars, **kwargs)
        
        elif self.type == self.InputType.NUMERIC:
            return model_field.formfield(min_value=self.numeric_min(),
                                         max_value=self.numeric_max(), **kwargs)
        
        # or use the ModelForm factory's default:
        return model_field.formfield(**kwargs)
    
    def clean_field(self, data, field):
        # currently, all are handled from validators set up on the form
        return data
    
    def numeric_min(self):
        if 'numeric_min' in self.options: return self.options['numeric_min']
        return None
    
    def numeric_max(self):
        if 'numeric_max' in self.options: return self.options['numeric_max']
        return None
    
    def default_value(self):
        if self.type == self.InputType.TEXT: return None
        
        if 'default_value' in self.options: return self.options['default_value']
        return None
    
    def conditional_value(self, value):
        if self.type in (self.InputType.TEXT, self.InputType.NUMERIC):
            # in this case, condition is whether the field was filled out
            # (and is non-zero for numeric)
            return bool(value)
        
        return value
    
    def span(self, media=None):
        width = 6
        if self.max_chars and self.max_chars > 50: width = 8
        if self.num_lines > 1: width = 8
        if self.num_lines > 4: width = 10
        if self.type in (self.InputType.CHOICE, self.InputType.BOOLEAN):
            width = 8
        elif self.type == self.InputType.NUMERIC: width = 2
        
        if self.type == self.InputType.NUMERIC:
            if 'span_phone' in self.options:
                return min(self.options['span_phone'], 4)

        if 'span_tablet' in self.options:
            if not media: return min(width, self.options['span_tablet'], 4)
        elif not media: return min(width, 4)
        
        if media == 'tablet' and 'span_tablet' in self.options:
            return self.options['span_tablet']
        if media == 'desktop' and 'span_desktop' in self.options:
            return self.options['span_desktop']
        
        return width
    
    def tablet_span(self): return self.span(media='tablet')
    def desktop_span(self): return self.span(media='desktop')


class CollectionBlock(FormBlock):
    class Meta:
        db_table = 'formative_formcollectionblock'
    
    FIXED_CHOICE_VAL_MAXLEN = 100
    
    class AlignType(models.TextChoices):
        HORIZONTAL = 'horizontal', _('horizontal')
        VERTICAL = 'vertical', _('vertical')
    
    block = models.OneToOneField(FormBlock, on_delete=models.CASCADE,
                                 parent_link=True, primary_key=True)
    fixed = models.BooleanField(default=False)
    min_items = models.PositiveIntegerField(null=True, blank=True) # null if
    max_items = models.PositiveIntegerField(null=True, blank=True) # fixed
    has_file = models.BooleanField(default=False)
    file_optional = models.BooleanField(default=False)
    # we don't need these references indexed or validated here, so no SlugField
    name1 = models.CharField(max_length=32, default='', blank=True)
    name2 = models.CharField(max_length=32, default='', blank=True)
    name3 = models.CharField(max_length=32, default='', blank=True)
    align_type = models.CharField(max_length=16, choices=AlignType.choices,
                                  default=AlignType.HORIZONTAL)
    
    def fields(self):
        return []
    
    def collection_fields(self):
        fields = []
        if self.name1: fields.append(self.name1)
        if self.name2: fields.append(self.name2)
        if self.name3: fields.append(self.name3)
        
        return fields
    
    def max_filesize(self):
        if 'max_filesize' in self.options: return self.options['max_filesize']
        return None # TODO: overall default max
    
    def allowed_filetypes(self):
        if 'file_types' in self.options:
            return self.options['file_types']
        
        return None # allow any file extension
    
    def allowed_extensions(self):
        types = self.allowed_filetypes()
        if not types: return None
        
        extensions = []
        for filetype in types:
            extensions += FileType.by_type(filetype)().allowed_extensions()
        return extensions
    
    def autoinit_filename(self):
        if 'autoinit_filename' in self.options: return True
        return False
    
    def fixed_choices(self):
        if 'choices' not in self.options:
            msg = 'choices must be provided for a fixed collection block'
            raise FieldError(msg)
        
        return self.options['choices']
    
    def num_choices(self):
        return len(self.fixed_choices())
    
    def file_limits(self):
        if 'file_limits' in self.options: return self.options['file_limits']
        return {}
    
    def process_options(self, filetype):
        if 'file_processing' not in self.options: return {}
        if filetype in self.options['file_processing']:
            return self.options['file_processing'][filetype]
        return {}
    
    def span(self, media=None):
        width = 10
        if media == 'tablet': width = 8

        if not media: return 4
        
        if media == 'tablet' and 'span_tablet' in self.options:
            return max(4, self.options['span_tablet'])
        if media == 'desktop' and 'span_desktop' in self.options:
            return max(4, self.options['span_desktop'])
        
        return width
    
    def tablet_span(self): return self.span(media='tablet')
    def desktop_span(self): return self.span(media='desktop')
    
    def total_colspan(self):
         fields = self.collection_fields()
         if fields: return len(fields)
         return 1
    
    def horizontal_width(self, field):
        total = self.total_colspan()
        if 'wide' in self.options:
            total += len(self.options['wide'])
            if field in self.options['wide']: return 200.0 / total
        return 100.0 / total
    
    def collection_fields_as_blocks(self):
        class ColFieldBlock:
            def __init__(self, name, width):
                self.name, self.width = name, width
        
        fields = self.collection_fields()
        return [ ColFieldBlock(n, self.horizontal_width(n)) for n in fields ]
    
    def items_sortable(self):
        return 'unsortable' not in self.options
    
    def button_text(self):
        if 'button_text' in self.options: return self.options['button_text']
        
        if self.has_file and not self.file_optional:
            if self.max_items and self.max_items > 1: return _('add files')
            return _('add file')
        return _('add item')


class SubmissionRecord(models.Model):
    class Meta:
        constraints = [
            UniqueConstraint(fields=['submission', 'type'],
                             name='unique_submission_record_type')
        ]
    
    class RecordType(models.TextChoices):
        FILES = 'files', _('uploaded files')
        SUBMISSION = 'submission', _('form submission')
    
    program = models.ForeignKey(Program, models.SET_NULL, null=True, blank=True)
    form = models.SlugField(max_length=64, allow_unicode=True)
    submission = models.UUIDField(editable=False)
    type = models.CharField(max_length=32)
    recorded = models.DateTimeField(auto_now=True, verbose_name='recorded at')
    text = models.TextField(blank=True)
    number = models.PositiveBigIntegerField(null=True, blank=True)
    deleted = models.BooleanField(default=False)

# abstract classes, used as templates for the dynamic models:

class Submission(models.Model):
    class Meta:
        abstract = True
    
    _id = models.UUIDField(primary_key=True, default=uuid.uuid4,
                           editable=False)
    # valid up to page N:
    _valid = models.PositiveIntegerField(default=0, editable=False)
    # an array of N block id arrays, those skipped for form dependency not met:
    _skipped = models.JSONField(default=list, blank=True, editable=False)
    _created = models.DateTimeField(auto_now_add=True)
    _modified = models.DateTimeField(auto_now=True)
    _submitted = models.DateTimeField(null=True, blank=True)
    
    @classmethod
    def _get_form(cls):
        program_slug = cls._meta.program_slug
        slug = cls._meta.model_name[len(program_slug)+1:]
        return Form.objects.get(program__db_slug=program_slug, db_slug=slug)
    
    def __str__(self):
        if hasattr(self, '_email'): return self._email
        return str(self._id)
    
    def _get_absolute_url(self):
        form = self._get_form()
        args = {'program_slug': form.program.slug, 'form_slug': form.slug,
                'sid': self._id}
        return reverse('submission', kwargs=args)
    
    def _update_context(self, form, context):
        context['review_link'] = submission_link(self, form, rest='review')
        
        for block in form.visible_blocks():
            if block.block_type() == 'custom':
                context[block.name] = getattr(self, block.name)
            elif block.block_type() == 'stock':
                class Obj: pass
                obj = Obj()
                obj.__dict__ = { n: getattr(self, block.stock.field_name(n))
                                 for n in block.stock.widget_names() }
                if len(obj.__dict__) > 1: context[block.name] = obj
                else: context[block.name] = next(iter(obj.__dict__.values()))
    
    def _send_email(self, form, name, **kwargs):
        form_emails = form.emails()
        if name in form_emails:
            subject = Template(form_emails[name]['subject'])
            template = Template(form_emails[name]['content'])
        else: subject, template = form.load_email_templates(name)
        
        context = {
            'submission': self, 'form': form,
            'submission_link': submission_link(self, form)
        }
        if self._submitted: self._update_context(form, context)
        
        return send_email(template=template, to=self._email,
                          subject=subject, context=context, **kwargs)
    
    def _submit(self):
        self._submitted = timezone.now()
        self.save()
    
    def _collections(self, queryset=None, form=None):
        if not form: form = self._get_form()
        if not queryset: queryset = self._items.all()
        
        # form's order also orders blocks' items with the same collection name
        block = FormBlock.objects.filter(form=form, pk=OuterRef('_block'))
        queryset = queryset.annotate(page=Subquery(block.values('page')))
        queryset = queryset.annotate(block_rank=Subquery(block.values('_rank')))
        items = queryset.order_by('_collection', 'page', 'block_rank', '_rank')
        collections = groupby(items, key=lambda item: item._collection)
        return { k: list(items) for k, items in collections }


def file_path(instance, filename):
    return os.path.join(str(instance._submission_id), filename)

class SubmissionItem(UnderscoredRankedModel):
    class Meta:
        abstract = True
    
    _id = models.BigAutoField(primary_key=True, editable=False)
    # see Form.item_model() for _submission = models.ForeignKey(Submission)
    
    # the item's collection name == the name of the CollectionBlock
    _collection = models.CharField(max_length=32)
    
    # id of the collection block this item came from, as some may have same name
    _block = models.PositiveBigIntegerField()
    
    _file = models.FileField(upload_to=file_path, max_length=172, blank=True)
    _filesize = models.PositiveBigIntegerField(default=0)
    _filemeta = models.JSONField(default=dict, blank=True)
    _error = models.BooleanField(default=False)
    _message = models.CharField(max_length=100, default='', blank=True)
    
    @classmethod
    def _filename_maxlen(cls):
        # use 37 for directory uuid, 8 for possible alt name, 7 for order prefix
        return cls._meta.get_field('_file').max_length - 37 - 8 - 7
    
    @classmethod
    def _message_maxlen(cls):
        return cls._meta.get_field('_message').max_length
    
    def _rank_group(self):
        return self.__class__.objects.filter(_submission=self._submission,
                                             _collection=self._collection,
                                             _block=self._block)
    
    def _file_name(self):
        if not self._file: return None
        return self._file.name[self._file.name.index('/')+1:]
    
    def _file_type(self):
        if 'type' in self._filemeta: return self._filemeta['type']
        return ''
    
    def _artifact_url(self, name='thumbnail'):
        if not self._file: return None
        type = self._file_type()
        if not type: return None
        if name != 'thumbnail' or type not in ('image', 'video'):
            filetype = FileType.by_type(type)()
            return filetype.artifact_url(name, self._file.url)
        
        if type == 'image': return thumbnail_path(self._file.url)
        elif type == 'video': return thumbnail_path(self._file.url, ext='jpg')
        return None
