from django.db import models

from . import StockWidget

class EmailWidget(StockWidget):
    TYPE = 'email'
    
    def __init__(self, name, **kwargs):
        super().__init__(name)
    
    def fields(self):
        return [(self.name, models.EmailField())]
