from django.core.exceptions import ValidationError
from django.db import models
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
        
        self.widgets = {
            'firstname': 'First name',
            'lastname': 'Last name'
        }
        self.required_part = required_part
    
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
                return { None: ValidationError(msg) }
