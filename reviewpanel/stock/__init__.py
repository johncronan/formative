__all__ = ["StockWidget", "EmailWidget", "NameWidget"]

class StockWidget:
    types = {}
    
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.TYPE: cls.types[cls.TYPE] = cls
    
    @classmethod
    def by_type(cls, type):
        return cls.types[type]
    
    def __init__(self, name):
        self.name = name
    
    def field_name(self):
        return '_' + self.name


class CompositeStockWidget(StockWidget):
    TYPE = None
    
    def field_name(self, field):
        # name has an initial underscore so that non-stock fields can't conflict
        return f'_{self.name}_{field}'


from .email import EmailWidget
from .name import NameWidget
