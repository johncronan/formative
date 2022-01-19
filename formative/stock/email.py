from django.db import models

from . import StockWidget

class EmailWidget(StockWidget):
    TYPE = 'email'
    
    def __init__(self, name, **kwargs):
        super().__init__(name, **kwargs)
        
        self.template_name = 'generic.html'
        self.review_template_name = 'review.html'
    
    def fields(self):
        field = models.EmailField(blank=True, null=True)
        if self.name == 'email':
            # only the validation block can use the name 'email' - needs unique
            field = models.EmailField(blank=True, unique=True)
        
        return [(self.field_name(), field)]
