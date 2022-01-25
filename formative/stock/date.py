from django.db import models
from django.forms import DateInput

from . import StockWidget

class DateWidget(StockWidget):
    TYPE = 'date'
    
    def __init__(self, name, **kwargs):
        super().__init__(name, **kwargs)
        
        self.template_name = 'date.html'
        self.review_template_name = 'review.html'
    
    def fields(self):
        field = models.DateField(null=True, blank=True)
        
        return [(self.field_name(), field)]
    
    def form_widget(self, name):
        return DateInput(format='%m/%d/%Y')
