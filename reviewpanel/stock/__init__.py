__all__ = ["StockWidget", "EmailWidget"]

class StockWidget:
    types = {}
    
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls.types[cls.TYPE] = cls
    
    @classmethod
    def by_type(cls, type):
        return cls.types[type]
    
    def __init__(self, name):
        self.name = name

from .email import EmailWidget
