from django.db import models, connection
from django.db.models import Q, Max, Case, Value, When, Exists, OuterRef, \
    UniqueConstraint, Subquery
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import FieldError, ValidationError
from django.utils.functional import cached_property
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from polymorphic.models import PolymorphicModel
import uuid
import markdown

from ..stock import StockWidget
from ..utils import create_model, remove_p, send_email
from .ranked import RankedModel, UnderscoredRankedModel
from .automatic import AutoSlugModel


class Program(AutoSlugModel):
    class Meta:
        ordering = ['created']
    
    name = models.CharField(max_length=32)
    slug = models.SlugField(max_length=32, unique=True, allow_unicode=True,
                            editable=False)
    db_slug = models.SlugField(max_length=32, unique=True, allow_unicode=True,
                               editable=False)
    description = models.CharField(max_length=200, blank=True)
    options = models.JSONField(default=dict, blank=True)
    hidden = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)
    

    def __str__(self):
        return self.name
    
    # TODO: disallow certain slug values, like "auth"
    
    @cached_property
    def markdown(self):
        return markdown.Markdown()
    
    def visible_forms(self):
        return self.forms.exclude(status=Form.Status.DRAFT)


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
    slug = models.SlugField(max_length=64, allow_unicode=True, editable=False)
    db_slug = models.SlugField(max_length=64, allow_unicode=True,
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
    
    @cached_property
    def model(self):
        if self.status == self.Status.DRAFT: return None
        
        fields = []
        for block in self.blocks.exclude(page=0, _rank__gt=1):
            fields += block.fields()
        
        name = self.db_slug
        return create_model(name, fields, table_prefix=self.program.db_slug,
                            base_class=Submission, meta=Submission.Meta)
    
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
        
        name = self.db_slug + '_item_'
        class Meta(SubmissionItem.Meta):
            constraints = [
                UniqueConstraint(fields=['_submission', '_collection',
                                         '_block', '_rank'],
                                 name=self.db_slug+'_unique_item_rank')
            ]
        return create_model(name, fields, table_prefix=self.program.db_slug,
                            base_class=SubmissionItem, meta=Meta)
    
    def publish_model(self, model):
        with connection.schema_editor() as editor:
            editor.create_model(model)
        ctype = ContentType(app_label=model._meta.app_label,
                            model=model.__name__)
        ctype.save()
        ContentType.objects.clear_cache()
    
    def unpublish_model(self, model):
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
        
        self.publish_model(self.model)
        if self.item_model: self.publish_model(self.item_model)
        
        self.save()
    
    def unpublish(self):
        if self.status == self.Status.DRAFT: return
        
        self.unpublish_model(self.model)
        if self.item_model: self.unpublish_model(self.item_model)
        
        self.status = self.Status.DRAFT
        if 'model' in self.__dict__: del self.model
        if 'item_model' in self.__dict__: del self.item_model
        
        self.save()

    def default_text_label_style(self):
        if 'default_text_label_style' in self.options:
            return self.options['default_text_label_style']
        return FormLabel.LabelStyle.WIDGET
    
    def num_pages(self):
        return self.blocks.aggregate(Max('page'))['page__max']
    
    def custom_blocks(self):
        return CustomBlock.objects.filter(form=self).non_polymorphic()
    
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

    def review_pre(self):
        if 'review_pre' in self.options:
            md = self.program.markdown
            return mark_safe(md.convert(self.options['review_pre']))
    
    def review_post(self):
        if 'review_post' in self.options:
            md = self.program.markdown
            return mark_safe(md.convert(self.options['review_post']))


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
        s = self.form.program.markdown.convert(self.text)
        if inline: return mark_safe(remove_p(s))
        return mark_safe(s)
    
    def display_inline(self):
        return self.display(inline=True)


class FormDependency(models.Model):
    class Meta:
        verbose_name_plural = 'form dependencies'
        constraints = [
            UniqueConstraint(fields=['block', 'value'], name='unique_blockval')
        ]
    
    block = models.ForeignKey('FormBlock', models.CASCADE,
                              related_name='dependencies',
                              related_query_name='dependency')
    value = models.CharField(max_length=64, blank=True)
    
    def __str__(self):
        return f'{self.block.dependence.name}="{self.value}"'


class FormBlock(PolymorphicModel, RankedModel):
    class Meta(PolymorphicModel.Meta, RankedModel.Meta):
        constraints = [
            UniqueConstraint(fields=['form', 'page', '_rank'],
                             name='unique_rank'),
#            UniqueConstraint(fields=['form', 'name'], name='unique_name')
#                             condition=~Q(instance_of=CollectionBlock))
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
    negate_dependencies = models.BooleanField(default=False)
    
    def __str__(self):
        return self.name
    
    def rank_group(self):
        return FormBlock.objects.filter(form=self.form, page=self.page)
    
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
        
        val = FormDependency.objects.filter(block_id=OuterRef('id'),
                                            value=Value(value))
        cond = Case(
            When(negate_dependencies=False, then=Exists(val)),
            When(negate_dependencies=True, then=~Exists(val))
        )
        query = query.annotate(en=cond).filter(en=True)
        return query.values_list('id', flat=True)
    
    def show_in_review(self):
        return True


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
            
            if self.num_lines > 1 or self.max_chars > self.DEFAULT_TEXT_MAXLEN:
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
        
        # or use the ModelForm factory's default:
        return model_field.formfield(**kwargs)
    
    def clean_field(self, data, field):
        # currently, all are handled from validators set up on the form
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
    
    def file_maxsize(self):
        if 'maxsize' in self.options: return self.options['maxsize']
        return None # TODO: overall default max
    
    def allowed_filetypes(self):
        if 'file_types' in self.options:
            return self.options['file_types']
        
        return None # allow any file extension
    
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
        return len(self.collection_fields())
    
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
            if self.max_items > 1: return _('add files')
            return _('add file')
        return _('add item')


# abstract classes, used as templates for the dynamic models:

class Submission(models.Model):
    class Meta:
        abstract = True
    
    _id = models.UUIDField(primary_key=True, default=uuid.uuid4,
                           editable=False)
    # valid up to page N:
    _valid = models.PositiveIntegerField(default=0, editable=False)
    # an array of N block id arrays, those skipped for form dependency not met:
    _skipped = models.JSONField(default=list, blank=True)
    _created = models.DateTimeField(auto_now_add=True)
    _modified = models.DateTimeField(auto_now=True)
    _submitted = models.DateTimeField(null=True, blank=True, editable=False)

    def _send_email(self, form, template, **kwargs):
        path = 'formative/emails/' + template
        return send_email(self, template=path, to=self._email,
                          context={'form': form},
                          context_object_name='submission', **kwargs)
    
    def _submit(self):
        self._submitted = timezone.now()
        self.save()


def file_path(instance, filename):
    return str(instance._submission_id) + '/' + filename

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
    _message = models.CharField(max_length=64, default='', blank=True)
    
    @classmethod
    def filename_maxlen(cls):
        # use 37 for directory uuid, 8 for possible alt name, 7 for order prefix
        return cls._meta.get_field('_file').max_length - 37 - 8 - 7
    
    def _rank_group(self):
        return self.__class__.objects.filter(_submission=self._submission,
                                             _collection=self._collection,
                                             _block=self._block)
    
    def _file_name(self):
        if not self._file: return None
        return self._file.name[self._file.name.index('/')+1:]
