from django.core.validators import RegexValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from . import StockWidget


class PhoneNumberWidget(StockWidget):
    TYPE = 'phone'
    
    def __init__(self, name, **kwargs):
        super().__init__(name, **kwargs)
        
        self.template_name = 'phone.html'
        self.review_template_name = 'review.html'
        
    def fields(self):
        field = models.CharField(max_length=32, blank=True)
        return [(self.field_name(), field)]

    def field_validators(self, widget=None):
        return [RegexValidator(r'^[0-9 .()/+-]*$',
                               message=_('Invalid phone number format.'))]
