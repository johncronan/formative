from django.db import models, connection
from django.db.models import Q, UniqueConstraint
from django.core.exceptions import FieldError
from django.utils.functional import cached_property
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from polymorphic.models import PolymorphicModel

from .stock import StockWidget
from .utils import create_model


class Program(models.Model):
    name = models.CharField(max_length=32)
    slug = models.SlugField(max_length=32, allow_unicode=True, editable=False)
    description = models.CharField(max_length=200, blank=True)
    
    def __str__(self):
        return self.name
    
    # TODO: disallow certain slug values, like "auth"
    def save(self, *args, **kwargs):
        if self._state.adding:
            self.slug = slugify(self.name).replace('-', '')
        super().save(*args, **kwargs)


class FormLabel(models.Model):
    class LabelStyle(models.TextChoices):
        OUTLINED = 'outlined', _('outlined text')
        VERTICAL = 'vertical', _('vertical label')
        HORIZONTAL = 'horizontal', _('horizontal label')
    
    path = models.CharField(max_length=128, primary_key=True)
    text = models.CharField(max_length=1000)
    style = models.CharField(max_length=16, choices=LabelStyle.choices)
    
    def __str__(self):
        return self.path


class Form(models.Model):
    class Meta:
        constraints = [
            UniqueConstraint(fields=['program', 'slug'], name='unique_slug')
        ]
    
    class Status(models.TextChoices):
        DRAFT = 'draft', _('unpublished')
        DISABLED = 'disabled', _('submissions disabled')
        ENABLED = 'enabled', _('published/enabled')
        COMPLETED = 'completed', _('completed')
    
    program = models.ForeignKey(Program, models.CASCADE)
    name = models.CharField(max_length=64)
    slug = models.SlugField(max_length=64, allow_unicode=True, editable=False)
    status = models.CharField(max_length=16, choices=Status.choices)
    # TODO: date stuff
    default_text_label_style = \
        models.CharField(max_length=16, choices=FormLabel.LabelStyle.choices,
                         default=FormLabel.LabelStyle.OUTLINED)
    
    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        if self._state.adding or self.status == self.Status.DRAFT:
            self.slug = slugify(self.name).replace('-', '')
        
        super().save(*args, **kwargs)
    
    @cached_property
    def model(self):
        if self.status == self.Status.DRAFT: return None
        
        fields = [] # TODO grab some model fields from SubmissionMeta
        for block in self.blocks.filter(page__gt=0): fields += block.fields()
        
        # add methods from SubmissionMeta
        fields += [(k, v) for k, v in SubmissionMeta.__dict__.items()
                   if callable(v) and not isinstance(v, type)]
        
        name = self.slug
        return create_model(name, fields, app_label=self.program.slug,
                            options=SubmissionMeta.Meta.__dict__)
    
    @cached_property
    def item_model(self):
        if self.status == self.Status.DRAFT: return None
        
        collections = self.collections()
        if not collections: return None
        
        names = []
        for c in collections:
            for field in c.collection_fields():
                if field not in names: names.append(field)
        
        fields = [] # TODO same as above re SubmissionItemMeta
        
        # the first column links submission items to the submission
        fields.append(('_submission',
                       models.ForeignKey(self.model, models.CASCADE)))
        
        # the next column identifies the item's collection name
        fields.append(('_collection', models.CharField(max_length=32)))
        
        for n in names:
            # look for a CustomBlock with the same name on page 0 (hidden)
            try:
                block = self.custom_blocks().get(page=0, name=n)
            # otherwise, use the default text CustomBlock
            except CustomBlock.DoesNotExist:
                block = CustomBlock.text_create()
            fields.append((n, block.field()))
        
        def path(instance, filename): return self.slug + '/'
        file_field = models.FileField(upload_to=path, max_length=128)
        fields.append(('_file', file_field))
        
        name = self.slug + '_item_'
        return create_model(name, fields, app_label=self.program.slug,
                            options=SubmissionItemMeta.Meta.__dict__)
    
    def publish(self):
        if self.status != self.Status.DRAFT: return
        
        self.status = self.Status.ENABLED
        if 'model' in self.__dict__: del self.model
        if 'item_model' in self.__dict__: del self.item_model
        
        with connection.schema_editor() as editor:
            editor.create_model(self.model)
            if self.item_model: editor.create_model(self.item_model)
        
        self.save()
    
    def unpublish(self):
        if self.status == self.Status.DRAFT: return
        
        with connection.schema_editor() as editor:
            editor.delete_model(self.model)
            if self.item_model: editor.delete_model(self.item_model)
        
        self.status = self.Status.DRAFT
        if 'model' in self.__dict__: del self.model
        if 'item_model' in self.__dict__: del self.item_model
        
        self.save()
    
    def custom_blocks(self):
        return self.blocks.instance_of(CustomBlock)
    
    def collections(self):
        return self.blocks.instance_of(CollectionBlock)


class FormBlock(PolymorphicModel):
    class Meta:
        constraints = [
            UniqueConstraint(fields=['form', 'page', 'rank'],
                             name='unique_rank'),
            UniqueConstraint(fields=['form', 'name'], name='unique_name')
#                             condition=~Q(instance_of=CollectionBlock))
        ]
        ordering = ['form', 'page', 'rank']
    
    form = models.ForeignKey(Form, models.CASCADE,
                             related_name='blocks', related_query_name='block')
    name = models.SlugField(max_length=32, verbose_name='identifier',
                            allow_unicode=True)
    options = models.JSONField(default=dict)
    rank = models.PositiveIntegerField(default=0)
    page = models.PositiveIntegerField(default=1)
    dependence = models.ForeignKey('FormBlock', models.CASCADE,
                                   null=True, blank=True,
                                   related_name='dependents',
                                   related_query_name='dependent')
    
    def __str__(self):
        return self.name
    
    def stock_type(self):
        if 'type' not in self.options:
            raise FieldError('untyped stock widget')
        
        return StockWidget.by_type(self.options['type'])
    
    @cached_property
    def stock(self):
        return self.stock_type()(self.name, **self.options)
    
    def fields(self):
        return self.stock.fields()


class FormDependency(models.Model):
    class Meta:
        verbose_name = 'form dependencies'
        constraints = [
            UniqueConstraint(fields=['block', 'value'], name='unique_blockval')
        ]
    
    block = models.ForeignKey(FormBlock, models.CASCADE,
                              related_name='dependencies',
                              related_query_name='dependency')
    value = models.CharField(max_length=64)
    
    def __str__(self):
        return f'{self.block}="{self.value}"'


class CustomBlock(FormBlock):
    class Meta:
        db_table = 'reviewpanel_formcustomblock'
    
    MAX_CHARS_PER_WORD = 10
    CHOICE_VAL_MAXLEN = 64
    DEFAULT_TEXT_MAXLEN = 1000
    
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
    
    def field(self):
        if self.type == self.InputType.TEXT:
            chars = self.max_chars
            if self.max_words and not chars:
                chars = self.max_words * self.MAX_CHARS_PER_WORD
            
            cls = models.TextField
            if chars and chars <= self.DEFAULT_TEXT_MAXLEN:
                cls = models.CharField
            
            return cls(max_length=chars)

        elif self.type == self.InputType.NUMERIC:
            if not self.required:
                return models.IntegerField(null=True, blank=True)
            return models.IntegerField()

        elif self.type == self.InputType.CHOICE:
            args = {'max_length': self.CHOICE_VAL_MAXLEN}
            return models.CharField(max_length=self.CHOICE_VAL_MAXLEN)
        
        elif self.type == self.InputType.BOOLEAN:
            return models.BooleanField(default=False)
    
    def fields(self):
        return [(self.name, self.field())]


class CollectionBlock(FormBlock):
    class Meta:
        db_table = 'reviewpanel_formcollectionblock'
    
    block = models.OneToOneField(FormBlock, on_delete=models.CASCADE,
                                 parent_link=True, primary_key=True)
    fixed = models.BooleanField(default=False)
    has_file = models.BooleanField(default=False)
    file_optional = models.BooleanField(default=False)
    # we don't need these references indexed or validated here, so no SlugField
    name1 = models.CharField(max_length=32, default='')
    name2 = models.CharField(max_length=32, default='')
    name3 = models.CharField(max_length=32, default='')
    
    def fields(self):
        return []
    
    def collection_fields(self):
        fields = []
        if self.name3: fields.insert(0, self.name3)
        if self.name2: fields.insert(0, self.name2)
        if self.name1: fields.insert(0, self.name1)
        
        return fields


class SubmissionMeta:
    class Meta:
        pass


class SubmissionItemMeta:
    class Meta:
        pass
