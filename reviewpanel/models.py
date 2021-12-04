from django.db import models, connection
from django.db.models import UniqueConstraint
from django.core.exceptions import FieldError
from django.utils.functional import cached_property
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from polymorphic.models import PolymorphicModel

from .stock import StockWidget
from .utils import create_model


class Program(models.Model):
    name = models.CharField(max_length=64)
    slug = models.SlugField(max_length=64, allow_unicode=True, editable=False)
    description = models.CharField(max_length=200, blank=True)
    
    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        if self._state.adding:
            self.slug = slugify(self.name).replace('-', '')
        super().save(*args, **kwargs)


class FormLabel(models.Model):
    class LabelStyle(models.TextChoices):
        OUTLINED = 'outlined', _('outlined text')
        VERTICAL = 'vertical', _('vertical label')
        HORIZONTAL = 'horizontal', _('horizontal label')
    
    path = models.CharField(max_length=64, primary_key=True)
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
        if self._state.adding:
            self.slug = slugify(self.name).replace('-', '')
        super().save(*args, **kwargs)
    
    @cached_property
    def model(self):
        if self.status == self.Status.DRAFT: return None
        
        fields = []
        for block in self.blocks.all(): fields += block.fields()
        
        # add methods from SubmissionMeta
        fields += [(k, v) for k, v in SubmissionMeta.__dict__.items()
                   if callable(v) and not isinstance(v, type)]
        
        name = self.slug
        return create_model(name, dict(fields), app_label=self.program.slug,
                            options=SubmissionMeta.Meta.__dict__)
    
    def publish(self):
        if self.status != self.Status.DRAFT: return
        
        self.status = self.Status.ENABLED
        del self.model
        with connection.schema_editor() as editor:
            editor.create_model(self.model)
        self.save()
        
    
    def unpublish(self):
        if self.status == self.Status.DRAFT: return
        
        with connection.schema_editor() as editor:
            editor.delete_model(self.model)
        self.status = self.Status.DRAFT
        del self.model
        self.save()


class FormBlock(PolymorphicModel):
    class Meta:
        constraints = [
            UniqueConstraint(fields=['form', 'page', 'rank'],
                             name='unique_rank'),
            UniqueConstraint(fields=['form', 'name'], name='unique_name')
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
                                   null=True, blank=True)
    
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
    
    block = models.ForeignKey(FormBlock, models.CASCADE)
    value = models.CharField(max_length=64)
    
    def __str__(self):
        return f'{self.block}="{self.value}"'


class CustomBlock(FormBlock):
    class Meta:
        db_table = 'reviewpanel_formcustomblock'
    
    MAX_CHARS_PER_WORD = 10
    CHOICE_VAL_MAXLEN = 64
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
    
    def field(self):
        if self.type == self.InputType.TEXT:
            chars = self.max_chars
            if self.max_words and not chars:
                chars = self.max_words * self.MAX_CHARS_PER_WORD
            
            cls = models.TextField
            if chars and chars <= 1000: cls = models.CharField
            
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


class SubmissionMeta:
    class Meta:
        pass
