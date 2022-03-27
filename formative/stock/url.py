from django.db import models
from django.utils.html import mark_safe

from . import StockWidget

class URLWidget(StockWidget):
    TYPE = 'url'
    
    def __init__(self, name, **kwargs):
        super().__init__(name, **kwargs)
        
        self.template_name = 'url.html'
        self.review_template_name = 'review.html'
    
    def fields(self):
        field = models.URLField(blank=True)
        
        return [(self.field_name(), field)]
    
    def clean(self, data):
        if '://' not in data[:8]:
            return 'http://' + data
        return data
    
    def render(self, choice, **kwargs):
        url = kwargs[self.name]
        if not url: return ''
        return mark_safe(f'<a target="_blank" href="{url}">{url}</a>')
        
