from django.db import models

from . import StockWidget

class URLWidget(StockWidget):
    TYPE = 'url'
    
    def __init__(self, name, **kwargs):
        super().__init__(name, **kwargs)
        
        self.template_name = 'generic.html'
        self.review_template_name = 'review.html'
    
    def fields(self):
        field = models.URLField(blank=True)
        
        return [(self.field_name(), field)]
