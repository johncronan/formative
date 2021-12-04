from django.db import models
from django.core.exceptions import FieldError
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from polymorphic.models import PolymorphicModel

from .stock import StockWidget


class Program(models.Model):
    name = models.CharField(max_length=64)
    description = models.CharField(max_length=200)
    
    def __str__(self):
        return self.name


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
    program = models.ForeignKey(Program, models.CASCADE)
    name = models.CharField(max_length=64)
    default_text_label_style = \
        models.CharField(max_length=16, choices=FormLabel.LabelStyle.choices,
                         default=FormLabel.LabelStyle.OUTLINED)
    
    def __str__(self):
        return self.name


class FormBlock(PolymorphicModel):
    form = models.ForeignKey(Form, models.CASCADE,
                             related_name='blocks', related_query_name='block')
    name = models.SlugField(max_length=32, verbose_name='identifier',
                            unique=True, allow_unicode=True)
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
            models.UniqueConstraint(fields=['block', 'value'],
                                    name='unique_blockval')
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

