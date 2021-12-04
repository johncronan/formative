from django.db import models

from . import StockWidget

class NameWidget(StockWidget):
    TYPE = 'name'
    
    def __init__(self, name, **kwargs):
        super().__init__(name)
    
    def fields(self):
        cls = models.CharField
        args = {'max_length': 32}
        
        parts = ('firstname', 'lastname')
        return [(f'_{self.name}_{field}', cls(**args)) for field in parts]
