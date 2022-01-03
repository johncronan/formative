from django.utils.text import capfirst

__all__ = ["StockWidget", "EmailWidget", "NameWidget"]


class StockWidget:
    types = {}
    
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
        return capfirst(self.name)

    def widget_labels(self):
        from ..models import FormLabel
        
        return {
            self.name: (FormLabel.LabelStyle.WIDGET, self.default_label())
        }


class CompositeStockWidget(StockWidget):
    TYPE = None

    def __init__(self, name, **kwargs):
        super().__init__(name, **kwargs)
        
        # dict mapping path names to default widget labels
        self.widgets = {}

    def widget_names(self): return self.widgets.keys()
    
    def field_names(self):
        return tuple(self.field_name(f) for f in self.widget_names())
    
    def field_name(self, field):
        # name has an initial underscore so that non-stock fields can't conflict
        return f'_{self.name}_{field}'

    def widget_labels(self):
        from ..models import FormLabel
        
        return { f'{self.name}.{name}': (FormLabel.LabelStyle.WIDGET, label)
                 for name, label in self.widgets.items() }


from .email import EmailWidget
from .name import NameWidget
