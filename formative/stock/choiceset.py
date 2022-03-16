from django.core.exceptions import ValidationError
from django.db import models
from django.forms import RadioSelect, CheckboxInput, CharField, BooleanField, \
    IntegerField
from django.utils.text import capfirst
from django.utils.translation import gettext_lazy as _
from django_better_admin_arrayfield.forms.fields import DynamicArrayField

from . import CompositeStockWidget


class ChoiceSetWidget(CompositeStockWidget):
    TYPE = 'choiceset'
    
    def __init__(self, name, choices=[], single=False, text_input=None,
                 text_input_maxlength=64, **kwargs):
        from ..signals import default_text
        
        super().__init__(name, **kwargs)
        
        self.template_name = 'choiceset.html'
        self.review_template_name = 'choiceset_review.html'
        
        self.single = single
        self.choices = choices
        self.labels = { name: default_text(name) for name in choices }
        if text_input: self.labels[text_input] = capfirst(text_input)
        self.text_input = text_input
        self.text_input_maxlength = text_input_maxlength
    
    def widget_names(self): # override for the ordering
        if self.single: names = [self.name]
        else: names = self.choices
        if self.text_input: return names + [self.text_input]
        return names
    
    def widget_labels(self):
        from ..models import FormLabel
        
        labels = super().widget_labels()
        labels[self.name] = (FormLabel.LabelStyle.VERTICAL,
                             self.default_label() + ':')
        return labels
    
    def fields(self):
        cls = models.BooleanField
        args = {'null': True}
        
        if not self.single:
            fields = [ (self.field_name(field), cls(**args))
                       for field in self.choices ]
        else:
            ml = max(len(name) for name in self.choices)
            choices = [ (k, self.labels[k]) for k in self.choices ]
            fields = [(self.field_name(self.name),
                      models.CharField(blank=True, max_length=ml,
                                       choices=choices, **args))]
        
        if self.text_input:
            ml = self.text_input_maxlength
            fields.append((self.field_name(self.text_input),
                           models.CharField(blank=True, max_length=ml, **args)))
        return fields
    
    def field_required(self, part):
        req = super().field_required(part)
        # TODO: single choice, required == True needs special handling w/ clean
        if self.single and req and part != self.text_input: return True
        return False
    
    def form_widget(self, name):
        if name != self.text_input:
            if self.single: return RadioSelect
            return CheckboxInput
        return super().form_widget(name)
    
    def admin_fields(self):
        from ..models import CustomBlock
        
        choices = DynamicArrayField(
            CharField(max_length=CustomBlock.CHOICE_VAL_MAXLEN)
        )
        single = BooleanField(label='single selection', required=False)
        text_input = CharField(label='text input ID', required=False,
                               max_length=30)
        max_length = IntegerField(label='max text characters', required=False,
                                  min_value=1, max_value=1000)
        
        f = super().admin_fields()
        f.update({'choices': choices, 'single': single,
                  'text_input': text_input, 'text_input_maxlength': max_length})
        return f
    
    def admin_clean(self, data):
        if 'text_input' in data and data['text_input']:
            if not data['text_input_maxlength']:
                err = ValidationError('required if there is a text input',
                                      code='required')
                return {'text_input_maxlength': err}
        return data
    
    def admin_published_readonly(self):
        return {'choices': 'choices', 'text_input': 'text input ID'}
    
    def render_choices(self):
        return [('with', 'with unlisted'), ('without', 'with [unlisted]'),
                ('exclude', 'without unlisted')]
    
    def render(self, choice, **kwargs):
        vals = []
        if self.single and kwargs[self.name]: vals.append(kwargs[self.name])
        else:
            for field in self.choices:
                if kwargs[field]: vals.append(field) # TODO: relabel?
        if choice != 'exclude' and self.text_input:
            if kwargs[self.text_input]:
                if choice == 'with': vals.append(kwargs[self.text_input])
                else: vals.append('[unlisted]')
            
        return ', '.join(vals)
