from django.forms import BooleanField
from django.utils.text import capfirst

__all__ = ["StockWidget", "EmailWidget", "NameWidget", "AddressWidget",
           "PhoneNumberWidget", "URLWidget", "ChoiceSetWidget", "DateWidget"]


class StockWidget:
    types = {}
    composite = False
    
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.TYPE: cls.types[cls.TYPE] = cls
    
    @classmethod
    def by_type(cls, type):
        return cls.types[type]
    
    @classmethod
    def default_options(cls):
        return { 'type': cls.TYPE }
    
    def __init__(self, name, required=False, **kwargs):
        self.name = name
        self.required = required
    
    def widget_names(self):
        return (self.name,)

    def field_name(self, *args):
        return '_' + self.name
    
    def field_names(self):
        return (self.field_name(),)

    def field_required(self, widget=None):
        return self.required
    
    def field_validators(self, widget=None):
        return []

    def default_label(self):
        from ..signals import default_text
        
        return default_text(self.name)
    
    def get_widget(self, field_name):
        return None # methods will be called w/ widget=None since all one field

    def widget_labels(self):
        from ..models import FormLabel
        
        return {
            self.name: (FormLabel.LabelStyle.WIDGET, self.default_label())
        }
    
    # (need to clarify 'widget' in this context) form_widget is Django's
    def form_widget(self, name):
        return None # use default
    
    def conditional_value(self, **kwargs):
        # default is to return a boolean that's True if we got some input
        return bool([v for v in kwargs.values() if v])
    
    def clean(self, data):
        return data
    
    def admin_fields(self):
        return {'required': BooleanField(required=False)}
    
    def admin_clean(self, data):
        return data
    
    def admin_published_readonly(self):
        return {}


class CompositeStockWidget(StockWidget):
    TYPE = None
    composite = True

    def __init__(self, name, **kwargs):
        super().__init__(name, **kwargs)
        
        # dict mapping path names to default widget labels
        self.labels = {}

    def widget_names(self): return self.labels.keys()
    
    def field_names(self):
        return tuple(self.field_name(f) for f in self.widget_names())
    
    def field_name(self, field):
        # name has an initial underscore so that non-stock fields can't conflict
        return f'_{self.name}_{field}'

    def get_widget(self, field_name):
        return field_name[1:][len(self.name)+1:]
    
    def widget_labels(self):
        from ..models import FormLabel
        
        labels = {}
        for name, label in self.labels.items():
            LabelStyle = FormLabel.LabelStyle
            if name is None: labels[self.name] = (LabelStyle.VERTICAL, label)
            else: labels[f'{self.name}.{name}'] = (LabelStyle.WIDGET, label)
        return labels
    
    def render_choices(self):
        return [('', '-')]
    
    # method to render a composite widget's values into a single string
    def render(self, choice, **kwargs):
        return ''


from .email import EmailWidget
from .name import NameWidget
from .address import AddressWidget
from .phone import PhoneNumberWidget
from .url import URLWidget
from .choiceset import ChoiceSetWidget
from .date import DateWidget
