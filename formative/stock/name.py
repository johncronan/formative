from django.core.exceptions import ValidationError
from django.db import models
from django.contrib.admin.widgets import AdminRadioSelect
from django.forms import ChoiceField
from django.utils.translation import gettext_lazy as _

from . import CompositeStockWidget


class NameWidget(CompositeStockWidget):
    TYPE = 'name'
    
    class Parts:
        ALL = 'all'
        LAST = 'last'
        ANY = 'any'
    
    def __init__(self, name, required_part=Parts.ALL, **kwargs):
        super().__init__(name, **kwargs)
        
        self.template_name = 'name.html'
        self.review_template_name = 'name_review.html'
        
        self.labels = {
            'firstname': 'First name',
            'lastname': 'Last name'
        }
        self.required_part = required_part
    
    def widget_names(self): return ('firstname', 'lastname')
    
    def fields(self):
        cls = models.CharField
        args = {'max_length': 32, 'blank': True}
        
        return [ (self.field_name(field), cls(**args))
                 for field in self.widget_names() ]
    
    def field_required(self, part):
        if not super().field_required(part): return False
        if self.required_part == self.Parts.ANY: return False
        if self.required_part == self.Parts.LAST and part == 'lastname':
            return True
        if self.required_part == self.Parts.ALL: return True
        return False
    
    def clean(self, data):
        if self.required_part == self.Parts.ANY:
            if all(not data[w] for w in self.widget_names()):
                msg = _('One of the name fields must be provided.')
                return {None: ValidationError(msg)}
        return data
    
    def admin_fields(self):
        required_part = ChoiceField(required=False, widget=AdminRadioSelect,
            choices=[(self.Parts.LAST, 'last name'),
                     (self.Parts.ANY, 'any part'),
                     (self.Parts.ALL, 'all parts')]
        )
        
        f = super().admin_fields()
        f['required_part'] = required_part
        return f
    
    def render_choices(self):
        return [('full', 'Full name')]
    
    def render(self, choice, **kwargs):
        return f"{kwargs['firstname']} {kwargs['lastname']}"
