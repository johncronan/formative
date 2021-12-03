from django.db import models
from django.core.exceptions import FieldError
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from polymorphic.models import PolymorphicModel

from .stock import StockWidget

class Program(models.Model):
    name = models.CharField(max_length=64)
    description = models.CharField(max_length=200)


class FormLabel(models.Model):
    class LabelStyle(models.TextChoices):
        OUTLINED = 'outlined', _('outlined text')
        VERTICAL = 'vertical', _('vertical label')
        HORIZONTAL = 'horizontal', _('horizontal label')
    
    path = models.CharField(max_length=32)
    text = models.CharField(max_length=1000)
    style = models.CharField(max_length=16, choices=LabelStyle.choices)


class Form(models.Model):
    name = models.CharField(max_length=64)
    default_text_label_style = \
        models.CharField(max_length=16, choices=FormLabel.LabelStyle.choices,
                         default=FormLabel.LabelStyle.OUTLINED)


class FormBlock(PolymorphicModel):
    name = models.SlugField(max_length=32, verbose_name='identifier',
                            unique=True, allow_unicode=True)
    options = models.JSONField(default=dict)
    rank = models.IntegerField(default=0)
    page = models.IntegerField(default=1)
    dependence = models.ForeignKey('FormBlock', models.CASCADE, null=True)
    
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


class CustomBlock(FormBlock):
    class Meta:
        db_table = 'reviewpanel_formcustomblock'
    
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
    num_lines = models.IntegerField(default=1)
    min_chars = models.IntegerField(null=True)
    max_chars = models.IntegerField(null=True)
    min_words = models.IntegerField(null=True)
    max_words = models.IntegerField(null=True)
    
    def fields(self):
        return [self.name]


class CollectionBlock(FormBlock):
    class Meta:
        db_table = 'reviewpanel_formcollectionblock'
    
    block = models.OneToOneField(FormBlock, on_delete=models.CASCADE,
                                 parent_link=True, primary_key=True)
    fixed = models.BooleanField(default=False)
    has_file = models.BooleanField(default=False)
    file_optional = models.BooleanField(default=False)
    # we don't need these references indexed or validated here, so no SlugField
    name1 = models.CharField(max_length=32, null=True)
    name2 = models.CharField(max_length=32, null=True)
    name3 = models.CharField(max_length=32, null=True)
    
    def fields(self):
        return []

