from django.db import models

from . import CompositeStockWidget

class NameWidget(CompositeStockWidget):
    TYPE = 'name'
    
    def __init__(self, name, **kwargs):
        super().__init__(name)
    
    def fields(self):
        cls = models.CharField
        args = {'max_length': 32}
        
        parts = ('firstname', 'lastname')
        return [(self.field_name(field), cls(**args)) for field in parts]
