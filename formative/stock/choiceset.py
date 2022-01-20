from django.core.exceptions import ValidationError
from django.db import models
from django.forms import RadioSelect, CheckboxInput
from django.utils.text import capfirst
from django.utils.translation import gettext_lazy as _

from . import CompositeStockWidget


class ChoiceSetWidget(CompositeStockWidget):
    TYPE = 'choiceset'
    
    def __init__(self, name, choices=[], single=False, text_input=None,
                 text_input_maxlength=64, **kwargs):
        super().__init__(name, **kwargs)
        
        self.template_name = 'choiceset.html'
        self.review_template_name = 'choiceset_review.html'
        
        self.single = single
        self.choices = choices
        self.labels = { name: capfirst(name) for name in choices }
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
