from django.db import models

from . import CompositeStockWidget

class NameWidget(CompositeStockWidget):
    TYPE = 'name'
    
    def __init__(self, name, **kwargs):
        super().__init__(name)
        
        self.template_name = 'name.html'
        self.widgets = {
            'firstname': 'First name',
            'lastname': 'Last name'
        }
    
    def fields(self):
        cls = models.CharField
        args = {'max_length': 32, 'blank': True}
        
        return [ (self.field_name(field), cls(**args))
                 for field in self.widget_names() ]
